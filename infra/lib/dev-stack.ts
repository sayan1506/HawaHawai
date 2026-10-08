import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';

export class DevStack extends Stack {
  constructor(scope: Construct, id: string, props: StackProps) {
    super(scope, id, props);
    const logGroup = new logs.LogGroup(this, 'HealthLogs', {
      logGroupName: 'hawahawai-dev-health-logs', retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const role = new iam.Role(this, 'HealthRole', {
      roleName: 'hawahawai-dev-health-role', assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
    });
    logGroup.grantWrite(role);
    const cache = new dynamodb.Table(this, 'EnvironmentCache', {
      tableName: 'hawahawai-dev-environment-cache', partitionKey: {name: 'cache_key', type: dynamodb.AttributeType.STRING},
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST, timeToLiveAttribute: 'expires_at',
      removalPolicy: RemovalPolicy.RETAIN,
    });
    role.addToPolicy(new iam.PolicyStatement({actions: ['dynamodb:GetItem'], resources: [cache.tableArn]}));
    const schoolProfile = JSON.parse(readFileSync(resolve(__dirname, '../../contracts/demo-school.json'), 'utf8'));
    if (!/^[a-z0-9-]+$/.test(schoolProfile.school_id)) throw new Error('Invalid cache-key prefix');
    role.addToPolicy(new iam.PolicyStatement({actions: ['dynamodb:PutItem', 'dynamodb:UpdateItem'], resources: [cache.tableArn],
      conditions: {'ForAllValues:StringLike': {'dynamodb:LeadingKeys': [`${schoolProfile.school_id}#*`]}}}));
    const aiCredentials = new secretsmanager.CfnSecret(this, 'AiCredentials', {
      name: 'hawahawai-dev-ai-credentials', description: 'HawaHawai backend-only Gemini/Groq credentials; populated out of band.',
    });
    aiCredentials.applyRemovalPolicy(RemovalPolicy.RETAIN);
    role.addToPolicy(new iam.PolicyStatement({actions: ['secretsmanager:GetSecretValue'], resources: [aiCredentials.ref]}));
    const health = new lambda.Function(this, 'HealthFunction', {
      functionName: 'hawahawai-dev-health', runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64, handler: 'app.handler',
      code: lambda.Code.fromAsset(resolve(__dirname, '../../.local/phase3-lambda-bundle')),
      // SDK imports are CPU-bound. This avoids 25s cold-start timeouts observed at 256 MB.
      memorySize: 512, timeout: Duration.seconds(25), role, logGroup,
      environment: {HAWAHAWAI_ENV: 'dev', HAWAHAWAI_CACHE_TABLE: cache.tableName,
        HAWAHAWAI_SCHOOL_PROFILE_JSON: readFileSync(resolve(__dirname, '../../contracts/demo-school.json'), 'utf8'),
        HAWAHAWAI_VERIFICATION_ENABLED: this.node.tryGetContext('phase1Verification') === 'true' ? 'true' : 'false',
        HAWAHAWAI_AI_SECRET_ARN: aiCredentials.ref, HAWAHAWAI_AI_PROVIDER: 'gemini',
        HAWAHAWAI_GEMINI_MODEL: 'gemini-2.5-flash', HAWAHAWAI_GROQ_MODEL: 'llama-3.3-70b-versatile'},
    });
    const defaultPolicy = role.node.findChild('DefaultPolicy').node.defaultChild as iam.CfnPolicy;
    defaultPolicy.policyName = 'hawahawai-dev-health-logs';
    const api = new apigw.HttpApi(this, 'Api', {
      apiName: 'hawahawai-dev-api', createDefaultStage: false,
      corsPreflight: {
        allowOrigins: ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:4173', 'http://localhost:4173'],
        allowMethods: [apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.POST], allowHeaders: ['content-type'],
        maxAge: Duration.minutes(5),
      },
    });
    api.addRoutes({path: '/health', methods: [apigw.HttpMethod.GET], integration: new HttpLambdaIntegration('HealthIntegration', health)});
    const environmentIntegration = new HttpLambdaIntegration('EnvironmentIntegration', health);
    for (const path of ['/v1/schools/{school_id}', '/v1/schools/{school_id}/air', '/v1/schools/{school_id}/forecast', '/v1/schools/{school_id}/grap', '/v1/schools/{school_id}/verdict']) {
      api.addRoutes({path, methods: [apigw.HttpMethod.GET], integration: environmentIntegration});
    }
    api.addRoutes({path: '/v1/schools/{school_id}/advisory', methods: [apigw.HttpMethod.GET, apigw.HttpMethod.POST], integration: environmentIntegration});
    new apigw.HttpStage(this, 'DevStage', {
      httpApi: api, stageName: '$default', autoDeploy: true,
      throttle: {rateLimit: 5, burstLimit: 10},
    });
    new CfnOutput(this, 'ApiBaseUrl', {value: api.apiEndpoint});
    new CfnOutput(this, 'HealthUrl', {value: `${api.apiEndpoint}/health`});
    new CfnOutput(this, 'HealthFunctionName', {value: health.functionName});
  }
}
