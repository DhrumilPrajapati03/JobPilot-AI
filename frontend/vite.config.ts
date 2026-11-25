import { defineConfig,loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({mode,command})=>{
  const env=loadEnv(mode,process.cwd(),'VITE_');
  const key=env.VITE_SUPABASE_ANON_KEY||'';
  let serviceRole=key.startsWith('sb_secret_');
  if(key.split('.').length===3){try{serviceRole ||= JSON.parse(Buffer.from(key.split('.')[1],'base64url').toString()).role==='service_role'}catch{throw new Error('Invalid frontend Supabase key')}}
  if(serviceRole)throw new Error('A server credential must never be included in the frontend build.');
  if(env.VITE_RELEASE_MODE==='true'){
    for(const name of ['VITE_SUPABASE_URL','VITE_API_BASE_URL','VITE_WS_BASE_URL']){
      let value:URL;try{value=new URL(env[name])}catch{throw new Error(name+' is required for a release build')}
      if(value.protocol!==(name==='VITE_WS_BASE_URL'?'wss:':'https:')||value.username||value.password)throw new Error(name+' must be a secure public origin');
    }
    if(!key)throw new Error('VITE_SUPABASE_ANON_KEY is required for a release build');
  }
  const origins=[env.VITE_SUPABASE_URL,env.VITE_API_BASE_URL,env.VITE_WS_BASE_URL].filter(Boolean).map(v=>new URL(v).origin);
  const policy="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob: https:; connect-src 'self' "+origins.join(' ')+"; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'";
  return {
  plugins: [
    react(),
    tailwindcss(),
    {name:'release-security-policy',transformIndexHtml:()=>command==='build'?[{tag:'meta',attrs:{'http-equiv':'Content-Security-Policy',content:policy},injectTo:'head'}]:[]},
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Long-lived vendor chunks cache across deploys.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          data: ['@tanstack/react-query', 'zustand'],
        },
      },
    },
  },
}})
