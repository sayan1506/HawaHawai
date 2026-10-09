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
import * as scheduler from 'aws-cdk-lib/aws-scheduler';
import * as amplify from 'aws-cdk-lib/aws-amplify';

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
    const schoolProfile = JSON.parse(readFileSync(resolve(__dirname, '../../contracts/demo-school.json'), 'utf8'));
    if (!/^[a-z0-9-]+$/.test(schoolProfile.school_id)) throw new Error('Invalid cache-key prefix');
    const writableKeys = [`${schoolProfile.school_id}#????????????#*`, `${schoolProfile.school_id}#advisory#*`, `${schoolProfile.school_id}#verdict#*`];
    role.addToPolicy(new iam.PolicyStatement({actions: ['dynamodb:GetItem'], resources: [cache.tableArn],
      conditions: {'ForAllValues:StringLike': {'dynamodb:LeadingKeys': [...writableKeys, `school#${schoolProfile.school_id}#profile`, 'regulatory#NCT_DELHI#*']}}}));
    role.addToPolicy(new iam.PolicyStatement({actions: ['dynamodb:PutItem', 'dynamodb:UpdateItem'], resources: [cache.tableArn],
      conditions: {'ForAllValues:StringLike': {'dynamodb:LeadingKeys': writableKeys}}}));
    const scheduleGroupName = 'hawahawai-dev-planning';
    const scheduleName = 'hawahawai-dev-daily-verdict';
    const scheduleArn = `arn:aws:scheduler:${this.region}:${this.account}:schedule/${scheduleGroupName}/${scheduleName}`;
    const aiCredentials = new secretsmanager.CfnSecret(this, 'AiCredentials', {
      name: 'hawahawai-dev-ai-credentials', description: 'HawaHawai backend-only Gemini/Groq credentials; populated out of band.',
    });
    aiCredentials.applyRemovalPolicy(RemovalPolicy.RETAIN);
    role.addToPolicy(new iam.PolicyStatement({actions: ['secretsmanager:GetSecretValue'], resources: [aiCredentials.ref]}));
    const health = new lambda.Function(this, 'HealthFunction', {
      functionName: 'hawahawai-dev-health', runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64, handler: 'app.handler',
      code: lambda.Code.fromAsset(resolve(__dirname, '../../.local/lambda-bundle')),
      // SDK imports are CPU-bound. This avoids 25s cold-start timeouts observed at 256 MB.
      memorySize: 512, timeout: Duration.seconds(25), role, logGroup,
      environment: {HAWAHAWAI_ENV: 'dev', HAWAHAWAI_CACHE_TABLE: cache.tableName,
        HAWAHAWAI_SCHOOL_PROFILE_JSON: readFileSync(resolve(__dirname, '../../contracts/demo-school.json'), 'utf8'),
        HAWAHAWAI_PROFILE_STORAGE_REQUIRED: 'true', HAWAHAWAI_DAILY_SCHEDULE_ARN: scheduleArn,
        HAWAHAWAI_VERIFICATION_ENABLED: this.node.tryGetContext('phase1Verification') === 'true' ? 'true' : 'false',
        HAWAHAWAI_AI_SECRET_ARN: aiCredentials.ref, HAWAHAWAI_AI_PROVIDER: 'gemini',
        HAWAHAWAI_GEMINI_MODEL: 'gemini-2.5-flash', HAWAHAWAI_GROQ_MODEL: 'llama-3.3-70b-versatile'},
    });
    const defaultPolicy = role.node.findChild('DefaultPolicy').node.defaultChild as iam.CfnPolicy;
    // Scheduler delivery retries and Lambda asynchronous execution retries are
    // independent. Bound both; don't retain failed planning events for six hours.
    new lambda.CfnEventInvokeConfig(this, 'PlanningAsyncConfig', {
      functionName: health.functionName, qualifier: '$LATEST',
      maximumRetryAttempts: 1, maximumEventAgeInSeconds: 900,
    });
    defaultPolicy.policyName = 'hawahawai-dev-health-logs';
    // Static manual deployments keep Git untouched. No repository token, build
    // role, SSR compute, additional bucket or custom domain is necessary.
    const frontend = new amplify.CfnApp(this, 'WebApp', {
      name: 'hawahawai-dev-web', platform: 'WEB',
      description: 'HawaHawai Phase 5 static PWA; manual artifact deployment.',
      enableBranchAutoDeletion: false,
      customHeaders: JSON.stringify({customHeaders: [
        {pattern: '**/*', headers: [
          {key: 'X-Content-Type-Options', value: 'nosniff'},
          {key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin'},
          {key: 'X-Frame-Options', value: 'DENY'},
          {key: 'Content-Security-Policy', value: "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://pu8l3a213j.execute-api.us-east-1.amazonaws.com; worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"},
          {key: 'Cache-Control', value: 'no-cache'},
        ]},
      ]}),
    });
    new amplify.CfnBranch(this, 'WebProduction', {
      appId: frontend.attrAppId, branchName: 'production', stage: 'PRODUCTION',
      enableAutoBuild: false, enablePullRequestPreview: false,
    });
    const frontendOrigin = `https://production.${frontend.attrDefaultDomain}`;
    const api = new apigw.HttpApi(this, 'Api', {
      apiName: 'hawahawai-dev-api', createDefaultStage: false,
      corsPreflight: {
        allowOrigins: ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:4173', 'http://localhost:4173', frontendOrigin],
        allowMethods: [apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.POST], allowHeaders: ['content-type'],
        maxAge: Duration.minutes(5),
      },
    });
    api.addRoutes({path: '/health', methods: [apigw.HttpMethod.GET], integration: new HttpLambdaIntegration('HealthIntegration', health)});
    const environmentIntegration = new HttpLambdaIntegration('EnvironmentIntegration', health);
    for (const path of ['/v1/schools/{school_id}', '/v1/schools/{school_id}/air', '/v1/schools/{school_id}/forecast', '/v1/schools/{school_id}/grap', '/v1/schools/{school_id}/verdict', '/v1/schools/{school_id}/verdict/history']) {
      api.addRoutes({path, methods: [apigw.HttpMethod.GET], integration: environmentIntegration});
    }
    api.addRoutes({path: '/v1/schools/{school_id}/advisory', methods: [apigw.HttpMethod.GET, apigw.HttpMethod.POST], integration: environmentIntegration});
    new apigw.HttpStage(this, 'DevStage', {
      httpApi: api, stageName: '$default', autoDeploy: true,
      throttle: {rateLimit: 5, burstLimit: 10},
    });
    new CfnOutput(this, 'ApiBaseUrl', {value: api.apiEndpoint});
    new CfnOutput(this, 'FrontendUrl', {value: frontendOrigin});
    new CfnOutput(this, 'FrontendAppId', {value: frontend.attrAppId});
    new CfnOutput(this, 'HealthUrl', {value: `${api.apiEndpoint}/health`});
    new CfnOutput(this, 'HealthFunctionName', {value: health.functionName});
    const planningGroup = new scheduler.CfnScheduleGroup(this, 'PlanningGroup', {name: scheduleGroupName});
    const plannerRole = new iam.Role(this, 'PlanningRole', {roleName: 'hawahawai-dev-planning-role',
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com', {conditions: {StringEquals: {
        'aws:SourceAccount': this.account, 'aws:SourceArn': planningGroup.attrArn}}})});
    plannerRole.addToPolicy(new iam.PolicyStatement({actions: ['lambda:InvokeFunction'], resources: [health.functionArn]}));
    (plannerRole.node.findChild('DefaultPolicy').node.defaultChild as iam.CfnPolicy).policyName = 'hawahawai-dev-planning-invoke';
    const refreshTime = this.node.tryGetContext('phase4RefreshTime') ?? '07:00';
    if (!/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(refreshTime)) throw new Error('Invalid planning time');
    const [hour, minute] = refreshTime.split(':');
    new scheduler.CfnSchedule(this, 'DailyPlanning', {name: scheduleName, groupName: planningGroup.ref,
      scheduleExpression: `cron(${Number(minute)} ${Number(hour)} * * ? *)`, scheduleExpressionTimezone: 'Asia/Kolkata',
      flexibleTimeWindow: {mode: 'OFF'}, state: 'ENABLED',
      target: {arn: health.functionArn, roleArn: plannerRole.roleArn, retryPolicy: {maximumEventAgeInSeconds: 900, maximumRetryAttempts: 1},
        input: JSON.stringify({job: 'hawahawai.daily-verdict.v1', school_id: schoolProfile.school_id,
          schedule_arn: '<aws.scheduler.schedule-arn>', scheduled_time: '<aws.scheduler.scheduled-time>'})}});
  }
}
