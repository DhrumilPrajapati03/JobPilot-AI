const {defineConfig}=require('@playwright/test');
const path=require('node:path');
const fs=require('node:fs');
process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.resolve(__dirname,'../.tool-cache/playwright');
const python=process.env.JOBPILOT_TEST_PYTHON || path.resolve(__dirname,process.platform==='win32'?'../backend/.venv/Scripts/python.exe':'../backend/.venv/bin/python');
const fixtureCwd=path.resolve(__dirname,'../.tool-cache/browser-api');fs.mkdirSync(fixtureCwd,{recursive:true});
const fixtureServer=path.resolve(__dirname,'../backend/tests/fixtures/browser_server.py');
module.exports=defineConfig({testDir:'e2e',timeout:60000,workers:1,reporter:'list',outputDir:'test-results',use:{baseURL:'http://127.0.0.1:5174',headless:true},webServer:[
  {command:`"${python}" "${fixtureServer}"`,cwd:fixtureCwd,url:'http://127.0.0.1:8001/health',timeout:90000,reuseExistingServer:false,env:{JOBPILOT_E2E:'1',PYTHONIOENCODING:'utf-8'}},
  {command:'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',url:'http://127.0.0.1:5174',timeout:60000,reuseExistingServer:false,env:{VITE_API_BASE_URL:'http://127.0.0.1:8001',VITE_WS_BASE_URL:'ws://127.0.0.1:8001',VITE_SUPABASE_URL:'https://e2e.supabase.test',VITE_SUPABASE_ANON_KEY:'synthetic-public-test-key'}}
]});
