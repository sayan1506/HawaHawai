import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';

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
    const health = new lambda.Function(this, 'HealthFunction', {
      functionName: 'hawahawai-dev-health', runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64, handler: 'index.handler',
      // Inline code avoids Docker bundling and Lambda code assets. CDK still publishes its stack template.
      code: lambda.Code.fromInline(readFileSync(resolve(__dirname, '../../backend/app.py'), 'utf8')),
      memorySize: 128, timeout: Duration.seconds(5), role, logGroup,
      environment: {HAWAHAWAI_ENV: 'dev'},
    });
    const defaultPolicy = role.node.findChild('DefaultPolicy').node.defaultChild as iam.CfnPolicy;
    defaultPolicy.policyName = 'hawahawai-dev-health-logs';
    const api = new apigw.HttpApi(this, 'Api', {
      apiName: 'hawahawai-dev-api', createDefaultStage: false,
      corsPreflight: {
        allowOrigins: ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:4173', 'http://localhost:4173'],
        allowMethods: [apigw.CorsHttpMethod.GET], allowHeaders: ['content-type'],
        maxAge: Duration.minutes(5),
      },
    });
    api.addRoutes({path: '/health', methods: [apigw.HttpMethod.GET], integration: new HttpLambdaIntegration('HealthIntegration', health)});
    new apigw.HttpStage(this, 'DevStage', {
      httpApi: api, stageName: '$default', autoDeploy: true,
      throttle: {rateLimit: 5, burstLimit: 10},
    });
    new CfnOutput(this, 'ApiBaseUrl', {value: api.apiEndpoint});
    new CfnOutput(this, 'HealthUrl', {value: `${api.apiEndpoint}/health`});
    new CfnOutput(this, 'HealthFunctionName', {value: health.functionName});
  }
}
