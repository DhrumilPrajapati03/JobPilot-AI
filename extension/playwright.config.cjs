const {defineConfig} = require('@playwright/test');
const path = require('node:path');
// Keep downloaded browsers and profiles out of source control.
process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.resolve(__dirname,'../.tool-cache/playwright');
module.exports = defineConfig({testDir:'tests/browser',testMatch:'*.spec.cjs',timeout:30000,workers:1,reporter:'list',use:{headless:true},outputDir:'test-results'});
