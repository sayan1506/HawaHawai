import { App, Tags } from 'aws-cdk-lib';
import { DevStack } from '../lib/dev-stack';

// The CLI profile is mandatory, and accidental deployment to a different account is rejected.
if (process.env.AWS_PROFILE !== 'hawahawai') throw new Error('Set AWS_PROFILE=hawahawai and pass --profile hawahawai');
const expectedAccount = '649437299529';
if (process.env.CDK_DEFAULT_ACCOUNT && process.env.CDK_DEFAULT_ACCOUNT !== expectedAccount) throw new Error('Wrong AWS account');
if (process.env.CDK_DEFAULT_REGION && process.env.CDK_DEFAULT_REGION !== 'us-east-1') throw new Error('Wrong AWS region');
const app = new App();
const stack = new DevStack(app, 'HawaHawaiDev', {
  env: {account: expectedAccount, region: 'us-east-1'},
  description: 'HawaHawai development health and environmental evidence API',
});
Tags.of(stack).add('project', 'hawahawai');
Tags.of(stack).add('environment', 'dev');
