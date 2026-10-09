import {defineConfig} from '@playwright/test';
import base from './playwright.config';
const prefix=process.env.HAWAHAWAI_TEST_EVIDENCE_PREFIX||'phase7';
export default defineConfig({...base,outputDir:`../.local/${prefix}-browser-results`,reporter:[['list'],['json',{outputFile:`../.local/${prefix}-browser-tests.json`}]]});
