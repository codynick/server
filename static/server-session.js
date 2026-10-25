'use strict';
(() => {
  const token = document.querySelector('meta[name=cn-server-csrf]')?.content;
  const originalFetch = window.fetch.bind(window);
  window.fetch = (resource, options = {}) => {
    const url = new URL(resource instanceof Request ? resource.url : resource, location.href);
    if (url.origin === location.origin) {
      const headers = new Headers(options.headers || (resource instanceof Request ? resource.headers : undefined));
      headers.set('X-CSRF-Token', token);
      options = {...options, headers};
    }
    return originalFetch(resource, options);
  };
  setInterval(() => originalFetch('/api/heartbeat', {method:'POST', headers:{'X-CSRF-Token':token}}).catch(()=>{}), 20000);
  addEventListener('DOMContentLoaded', () => {
    const bar = document.createElement('div');
    bar.style.cssText='position:fixed;right:12px;bottom:8px;z-index:10000;display:flex;gap:6px;background:white;padding:5px;border:1px solid #ccd5df;border-radius:4px;font:13px Arial';
    const home = document.createElement('button');home.onclick=()=>location.href='/';home.textContent='Main Panel';
    const logout = document.createElement('button');logout.textContent='Sign Out';
    logout.onclick=async()=>{const r=await fetch('/api/logout',{method:'POST'});if(r.ok)location.href='/';};
    bar.append(home,logout);document.body.append(bar);
  });
})();
