import {defineConfig} from '@playwright/test';
import base from './playwright.config';
export default defineConfig({...base,outputDir:'../.local/phase6-browser-results',reporter:[['list'],['json',{outputFile:'../.local/phase6-browser-tests.json'}]]});
