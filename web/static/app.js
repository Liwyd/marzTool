const GB=1024*1024*1024;
let currentPage='dashboard';
const PAGE_SIZE=25;
const pagState={};

document.addEventListener('DOMContentLoaded',()=>{
  initNav();
  initTheme();
  loadDashboard();
});

function initNav(){
  document.querySelectorAll('.nav-links li').forEach(li=>{
    li.addEventListener('click',()=>{
      document.querySelectorAll('.nav-links li').forEach(l=>l.classList.remove('active'));
      li.classList.add('active');
      const page=li.dataset.page;
      document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
      document.getElementById('page-'+page).classList.add('active');
      currentPage=page;
      loadPage(page);
    });
  });
}

function initTheme(){
  const saved=localStorage.getItem('theme')||'dark';
  document.documentElement.setAttribute('data-theme',saved);
  document.getElementById('themeToggle').addEventListener('click',()=>{
    const cur=document.documentElement.getAttribute('data-theme');
    const next=cur==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',next);
    localStorage.setItem('theme',next);
  });
}

function loadPage(page){
  const loaders={
    dashboard:loadDashboard,
    counter:loadCounter,
    bandwidth:loadVCounter,
    iplimit:loadIpLimits,
    traffic:()=>{loadExempt();loadVolumeNotifs();loadVolumeConfig();},
    users:loadUsers,
    subadmin:()=>{loadCounterSubAdmins();loadVCounterSubAdmins();},
    settlement:loadSettlement,
    telegram:()=>{},
    settings:loadSettings,
    services:()=>{loadDaemonStatus();loadDaemonLogs();loadWebDaemonStatus();},
  };
  if(loaders[page])loaders[page]();
}

async function api(path,opts={}){
  try{
    const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
    return await r.json();
  }catch(e){return{error:e.message};}
}

function toast(msg,type='info'){
  const t=document.createElement('div');
  t.className='toast toast-'+type;
  t.textContent=msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(),3000);
}

function fmt(b){return(b/GB).toFixed(2);}
function fmtDate(s){return s?s.substring(0,16).replace('T',' '):'-';}

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function paginate(arr,key,page){
  pagState[key]=pagState[key]||{page:1};
  if(page!==undefined)pagState[key].page=page;
  const p=pagState[key].page;
  const total=arr.length;
  const totalPages=Math.ceil(total/PAGE_SIZE)||1;
  if(p>totalPages)pagState[key].page=totalPages;
  const cp=pagState[key].page;
  const start=(cp-1)*PAGE_SIZE;
  return{items:arr.slice(start,start+PAGE_SIZE),page:cp,totalPages,total};
}

function pagerHtml(key,total,totalPages,fnName){
  if(totalPages<=1)return'';
  const cp=pagState[key].page;
  let h=`<div class="pager"><span class="pager-info">${total} items</span><div class="pager-btns">`;
  h+=`<button class="btn btn-sm" onclick="${fnName}(1)"${cp===1?' disabled':''}>&laquo;</button>`;
  h+=`<button class="btn btn-sm" onclick="${fnName}(${cp-1})"${cp===1?' disabled':''}>&lsaquo;</button>`;
  h+=`<span class="pager-cur">${cp} / ${totalPages}</span>`;
  h+=`<button class="btn btn-sm" onclick="${fnName}(${cp+1})"${cp===totalPages?' disabled':''}>&rsaquo;</button>`;
  h+=`<button class="btn btn-sm" onclick="${fnName}(${totalPages})"${cp===totalPages?' disabled':''}>&raquo;</button>`;
  h+=`</div></div>`;
  return h;
}

// DASHBOARD
async function loadDashboard(page){
  const d=await api('/api/summary');
  if(d.error)return;
  document.getElementById('summaryCards').innerHTML=`
    <div class="stat-card"><div class="stat-label">Total Users</div><div class="stat-value primary">${d.total_users}</div></div>
    <div class="stat-card"><div class="stat-label">Active Users</div><div class="stat-value success">${d.active_users}</div></div>
    <div class="stat-card"><div class="stat-label">Admins</div><div class="stat-value info">${d.admin_count}</div></div>
    <div class="stat-card"><div class="stat-label">Exempt</div><div class="stat-value warning">${d.exempt_count}</div></div>
  `;
  const allAdmins=new Set();
  (d.counter_totals||[]).forEach(c=>allAdmins.add(c.admin_username));
  (d.vcounter_totals||[]).forEach(v=>allAdmins.add(v.admin_username));
  Object.keys(d.admins||{}).forEach(a=>allAdmins.add(a));
  const allRows=[];
  allAdmins.forEach(a=>{
    const ct=(d.counter_totals||[]).find(c=>c.admin_username===a);
    const vt=(d.vcounter_totals||[]).find(v=>v.admin_username===a);
    allRows.push({admin:a,configs:d.admins[a]||'-',counter:ct?ct.total_count:'-',volume:vt?fmt(vt.total_volume_bytes):'-'});
  });
  const p=paginate(allRows,'dash',page);
  const tb=document.querySelector('#adminTable tbody');
  tb.innerHTML=p.items.map(r=>`<tr><td>${escHtml(r.admin)}</td><td>${r.configs}</td><td>${r.counter}</td><td>${r.volume}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No data</td></tr>';
  document.getElementById('adminPager').innerHTML=pagerHtml('dash',p.total,p.totalPages,'loadDashboard');
}

// COUNTER
async function loadCounter(page){
  const d=await api('/api/counter/report?viewer=web');
  if(d.error)return;
  document.getElementById('counterCards').innerHTML=`
    <div class="stat-card"><div class="stat-label">Total Count</div><div class="stat-value primary">${d.total}</div></div>
    <div class="stat-card"><div class="stat-label">Admins</div><div class="stat-value info">${d.admins.length}</div></div>
  `;
  const p=paginate(d.admins,'ct',page);
  document.querySelector('#counterTable tbody').innerHTML=p.items.map(a=>`<tr><td>${escHtml(a.admin_username)}</td><td><strong>${a.total_count}</strong></td><td><button class="btn btn-sm btn-primary" onclick="settleCounter('${escHtml(a.admin_username)}')">Settle</button></td></tr>`).join('')||'<tr><td colspan="3" class="empty">No data</td></tr>';
  document.getElementById('counterPager').innerHTML=pagerHtml('ct',p.total,p.totalPages,'loadCounter');
  const s=await api('/api/counter/settlements');
  const sp=paginate(s.settlements||(),'ct_s',page);
  document.querySelector('#counterSettlements tbody').innerHTML=sp.items.map(x=>`<tr><td>${escHtml(x.admin_username)}</td><td>${escHtml(x.settled_by)}</td><td>${x.amount_count}</td><td>${fmtDate(x.settled_at)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No settlements</td></tr>';
  document.getElementById('counterSettlementsPager').innerHTML=pagerHtml('ct_s',sp.total,sp.totalPages,'loadCounter');
}

async function settleCounter(admin){
  if(!confirm('Settle '+admin+'?'))return;
  const d=await api('/api/counter/settle',{method:'POST',body:JSON.stringify({admin_username:admin,settled_by:'web'})});
  if(d.error){toast(d.error,'error');return;}
  toast('Settled '+d.settled+' configs','success');
  loadCounter();
}

async function resetCounter(){
  if(!confirm('Reset ALL counters? This cannot be undone.'))return;
  await api('/api/counter/reset',{method:'POST',body:JSON.stringify({})});
  toast('Counters reset','success');
  loadCounter();
}

// VCOUNTER
async function loadVCounter(page){
  const d=await api('/api/vcounter/report?viewer=web');
  if(d.error)return;
  document.getElementById('vcounterCards').innerHTML=`
    <div class="stat-card"><div class="stat-label">Total Volume</div><div class="stat-value primary">${fmt(d.total_bytes)} GB</div></div>
    <div class="stat-card"><div class="stat-label">Admins</div><div class="stat-value info">${d.admins.length}</div></div>
  `;
  const p=paginate(d.admins,'vc',page);
  document.querySelector('#vcounterTable tbody').innerHTML=p.items.map(a=>`<tr><td>${escHtml(a.admin_username)}</td><td><strong>${fmt(a.total_volume_bytes)} GB</strong></td><td><button class="btn btn-sm btn-primary" onclick="settleVCounter('${escHtml(a.admin_username)}')">Settle</button></td></tr>`).join('')||'<tr><td colspan="3" class="empty">No data</td></tr>';
  document.getElementById('vcounterPager').innerHTML=pagerHtml('vc',p.total,p.totalPages,'loadVCounter');
  const s=await api('/api/vcounter/settlements');
  const sp=paginate(s.settlements||(),'vc_s',page);
  document.querySelector('#vcounterSettlements tbody').innerHTML=sp.items.map(x=>`<tr><td>${escHtml(x.admin_username)}</td><td>${escHtml(x.settled_by)}</td><td>${fmt(x.amount_bytes)}</td><td>${fmtDate(x.settled_at)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No settlements</td></tr>';
  document.getElementById('vcounterSettlementsPager').innerHTML=pagerHtml('vc_s',sp.total,sp.totalPages,'loadVCounter');
}

async function settleVCounter(admin){
  if(!confirm('Settle '+admin+'?'))return;
  const d=await api('/api/vcounter/settle',{method:'POST',body:JSON.stringify({admin_username:admin,settled_by:'web'})});
  if(d.error){toast(d.error,'error');return;}
  toast('Settled '+fmt(d.settled)+' GB','success');
  loadVCounter();
}

// IP LIMIT
async function loadIpLimits(page){
  const d=await api('/api/ip/limits');
  if(d.error)return;
  const entries=Object.entries(d.limits||{});
  const p=paginate(entries.map(([u,l])=>({u,l})),'ip',page);
  document.querySelector('#ipTable tbody').innerHTML=p.items.map(r=>`<tr><td>${escHtml(r.u)}</td><td>${r.l}</td></tr>`).join('')||'<tr><td colspan="2" class="empty">No limits set</td></tr>';
  document.getElementById('ipPager').innerHTML=pagerHtml('ip',p.total,p.totalPages,'loadIpLimits');
}

async function setIpLimit(){
  const u=document.getElementById('ipUsername').value.trim();
  const l=document.getElementById('ipLimit').value;
  if(!u)return toast('Enter username','error');
  await api('/api/ip/set',{method:'POST',body:JSON.stringify({username:u,limit:parseInt(l)})});
  toast('IP limit set','success');loadIpLimits();
}

async function deleteIpLimit(){
  const u=document.getElementById('ipUsername').value.trim();
  if(!u)return toast('Enter username','error');
  await api('/api/ip/delete',{method:'POST',body:JSON.stringify({username:u})});
  toast('IP limit removed','success');loadIpLimits();
}

// FLOW
async function flowSet(){
  const d=await api('/api/flow/set',{method:'POST',body:JSON.stringify({flow_value:'xtls-rprx-vision'})});
  if(d.error){toast(d.error,'error');return;}
  document.getElementById('flowResult').innerHTML=`<p>Done. Updated: ${d.updated} | Errors: ${d.errors}</p>`;
  toast('Flow set','success');
}
async function flowClear(){
  const d=await api('/api/flow/clear',{method:'POST',body:JSON.stringify({})});
  if(d.error){toast(d.error,'error');return;}
  document.getElementById('flowResult').innerHTML=`<p>Done. Updated: ${d.updated} | Errors: ${d.errors}</p>`;
  toast('Flow cleared','success');
}

// VOLUME
async function loadVolumeConfig(){
  const d=await api('/api/settings');
  if(d.error)return;
  document.getElementById('volLimitGb').value=d.volume_limit_gb||250;
  document.getElementById('volEnabled').checked=d.volume_limit_enabled;
}

async function saveVolumeConfig(){
  const gb=parseInt(document.getElementById('volLimitGb').value);
  const en=document.getElementById('volEnabled').checked;
  await api('/api/volume/config',{method:'POST',body:JSON.stringify({limit_gb:gb,enabled:en})});
  toast('Volume config saved','success');
}

async function loadExempt(page){
  const d=await api('/api/volume/exempt');
  if(d.error)return;
  const items=(d.exempt||[]);
  const p=paginate(items,'ex',page);
  document.querySelector('#exemptTable tbody').innerHTML=p.items.map(e=>`<tr><td>${escHtml(e.username)}</td><td>${fmtDate(e.added_at)}</td></tr>`).join('')||'<tr><td colspan="2" class="empty">No exempt users</td></tr>';
  document.getElementById('exemptPager').innerHTML=pagerHtml('ex',p.total,p.totalPages,'loadExempt');
}

async function addExempt(){
  const u=document.getElementById('exemptUsername').value.trim();
  if(!u)return toast('Enter username','error');
  await api('/api/volume/exempt/add',{method:'POST',body:JSON.stringify({username:u})});
  toast('User exempted','success');document.getElementById('exemptUsername').value='';loadExempt();
}
async function removeExempt(){
  const u=document.getElementById('exemptUsername').value.trim();
  if(!u)return toast('Enter username','error');
  await api('/api/volume/exempt/remove',{method:'POST',body:JSON.stringify({username:u})});
  toast('User removed','success');loadExempt();
}

async function loadVolumeNotifs(page){
  const d=await api('/api/volume/notifications');
  if(d.error)return;
  const p=paginate(d.notifications||(),'vn',page);
  document.querySelector('#volNotifTable tbody').innerHTML=p.items.map(n=>`<tr><td>${escHtml(n.username)}</td><td>${escHtml(n.admin_username||'-')}</td><td>${fmt(n.used_traffic_bytes)}</td><td>${fmtDate(n.disabled_at)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No disabled users</td></tr>';
  document.getElementById('volNotifPager').innerHTML=pagerHtml('vn',p.total,p.totalPages,'loadVolumeNotifs');
}

// USERS
async function loadUsers(page){
  const d=await api('/api/users');
  if(d.error){toast('Not connected to panel','error');return;}
  const users=d.users||[];
  const p=paginate(users,'us',page);
  document.querySelector('#usersTable tbody').innerHTML=p.items.map(u=>`<tr><td>${escHtml(u.username)}</td><td><span class="badge badge-${u.status==='active'?'success':'danger'}">${u.status}</span></td><td>${escHtml(u.admin)}</td><td>${u.data_limit?fmt(u.data_limit)+' GB':'Unlimited'}</td><td>${fmt(u.used_traffic)} GB</td><td>${fmtDate(u.created_at)}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">No users</td></tr>';
  document.getElementById('usersPager').innerHTML=pagerHtml('us',p.total,p.totalPages,'loadUsers');
}

// SUB-ADMINS
async function loadCounterSubAdmins(){
  const d=await api('/api/subadmin/counter');
  if(d.error)return;
  document.querySelector('#saCounterTable tbody').innerHTML=(d.sub_admins||[]).map(s=>`<tr><td>${s.telegram_id}</td><td>${escHtml(s.allowed_admins)}</td></tr>`).join('')||'<tr><td colspan="2" class="empty">No sub-admins</td></tr>';
}
async function addCounterSubAdmin(){
  const tid=document.getElementById('saTgId').value.trim();
  const admins=document.getElementById('saAdmins').value.trim().split(',').map(s=>s.trim()).filter(Boolean);
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/counter/add',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid),allowed_admins:admins})});
  toast('Added','success');loadCounterSubAdmins();
}
async function removeCounterSubAdmin(){
  const tid=document.getElementById('saTgId').value.trim();
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/counter/remove',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid)})});
  toast('Removed','success');loadCounterSubAdmins();
}
async function loadVCounterSubAdmins(){
  const d=await api('/api/subadmin/vcounter');
  if(d.error)return;
  document.querySelector('#saVCounterTable tbody').innerHTML=(d.sub_admins||[]).map(s=>`<tr><td>${s.telegram_id}</td><td>${escHtml(s.allowed_admins)}</td></tr>`).join('')||'<tr><td colspan="2" class="empty">No sub-admins</td></tr>';
}
async function addVCounterSubAdmin(){
  const tid=document.getElementById('vcSaTgId').value.trim();
  const admins=document.getElementById('vcSaAdmins').value.trim().split(',').map(s=>s.trim()).filter(Boolean);
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/vcounter/add',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid),allowed_admins:admins})});
  toast('Added','success');loadVCounterSubAdmins();
}
async function removeVCounterSubAdmin(){
  const tid=document.getElementById('vcSaTgId').value.trim();
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/vcounter/remove',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid)})});
  toast('Removed','success');loadVCounterSubAdmins();
}

// TELEGRAM
async function testTelegram(){
  document.getElementById('tgResult').innerHTML='<p>Testing...</p>';
  const d=await api('/api/telegram/test',{method:'POST',body:JSON.stringify({})});
  document.getElementById('tgResult').innerHTML=d.ok?`<p style="color:var(--success)">${d.message}</p>`:`<p style="color:var(--danger)">${d.message}</p>`;
}

function toggleFeature(btn){
  btn.classList.toggle('on');
  updateFeatureSubRows();
}

function updateFeatureSubRows(){
  document.getElementById('flowValueRow').style.display=document.getElementById('setFlow').classList.contains('on')?'flex':'none';
  document.getElementById('ipValueRow').style.display=document.getElementById('setIp').classList.contains('on')?'flex':'none';
  document.getElementById('volValueRow').style.display=document.getElementById('setVol').classList.contains('on')?'flex':'none';
  const tgOn=document.getElementById('setTg').classList.contains('on');
  document.getElementById('tgValueRow').style.display=tgOn?'flex':'none';
  document.getElementById('tgAdminRow').style.display=tgOn?'flex':'none';
}

// SETTINGS
async function loadSettings(){
  const d=await api('/api/settings');
  if(d.error)return;
  document.getElementById('setUrl').value=d.server_url||'';
  document.getElementById('setUser').value=d.username||'';
  document.getElementById('setFlowVal').value=d.flow_value||'xtls-rprx-vision';
  setToggle('setFlow',d.flow_enabled);
  setToggle('setIp',d.ip_limit_enabled);
  document.getElementById('setIpAll').value=d.ip_limit_all||1;
  setToggle('setCounter',d.counter_enabled);
  setToggle('setVcounter',d.vcounter_enabled);
  setToggle('setVol',d.volume_limit_enabled);
  document.getElementById('setVolGb').value=d.volume_limit_gb||250;
  setToggle('setTg',d.telegram_enabled);
  document.getElementById('setTgToken').value=d.telegram_token||'';
  document.getElementById('setTgAdmin').value=d.telegram_admin_id||'';
  document.getElementById('setInterval').value=d.daemon_interval||20;
  document.getElementById('setBanTime').value=d.ban_time||4;
  document.getElementById('setSshPort').value=d.ssh_port||22;
  document.getElementById('sslDomain').value=d.ssl_domain||'';
  const hasSsl=d.ssl_cert&&d.ssl_key;
  document.getElementById('sslStatus').innerHTML=hasSsl?`<span class="badge badge-success">SSL Active</span> ${escHtml(d.ssl_cert)}`:`<span class="badge badge-warning">No SSL</span>`;
  updateFeatureSubRows();
}

function setToggle(id,on){
  const btn=document.getElementById(id);
  if(on)btn.classList.add('on');
  else btn.classList.remove('on');
}

function getToggle(id){
  return document.getElementById(id).classList.contains('on');
}

async function saveSettings(){
  const pass=document.getElementById('setPass').value;
  const data={
    server_url:document.getElementById('setUrl').value,
    username:document.getElementById('setUser').value,
    flow_value:document.getElementById('setFlowVal').value,
    flow_enabled:getToggle('setFlow'),
    ip_limit_enabled:getToggle('setIp'),
    ip_limit_all:parseInt(document.getElementById('setIpAll').value),
    counter_enabled:getToggle('setCounter'),
    vcounter_enabled:getToggle('setVcounter'),
    volume_limit_enabled:getToggle('setVol'),
    volume_limit_gb:parseInt(document.getElementById('setVolGb').value),
    telegram_enabled:getToggle('setTg'),
    telegram_token:document.getElementById('setTgToken').value,
    telegram_admin_id:document.getElementById('setTgAdmin').value,
    daemon_interval:parseInt(document.getElementById('setInterval').value),
    ban_time:parseInt(document.getElementById('setBanTime').value),
    ssh_port:parseInt(document.getElementById('setSshPort').value),
  };
  if(pass)data.password=pass;
  const d=await api('/api/settings',{method:'POST',body:JSON.stringify(data)});
  if(d.error){toast(d.error,'error');return;}
  toast('Settings saved','success');
}

// SSL
async function getSslCert(){
  const domain=document.getElementById('sslDomain').value.trim();
  const email=document.getElementById('sslEmail').value.trim();
  if(!domain)return toast('Enter domain','error');
  if(!email)return toast('Enter email','error');
  document.getElementById('sslResult').innerHTML='<p style="color:var(--info)">Obtaining SSL certificate... This may take a minute.</p>';
  const d=await api('/api/ssl/get',{method:'POST',body:JSON.stringify({domain,email})});
  if(d.ok){
    document.getElementById('sslResult').innerHTML=`<p style="color:var(--success)">SSL obtained via ${d.used}. Cert: ${d.cert}</p>`;
    document.getElementById('sslStatus').innerHTML=`<span class="badge badge-success">SSL Active</span> ${escHtml(d.cert)}`;
    toast('SSL certificate obtained','success');
  }else{
    document.getElementById('sslResult').innerHTML=`<p style="color:var(--danger)">${escHtml(d.error||'Failed')}</p>`;
    toast('SSL failed','error');
  }
}

// SETTLEMENTS
async function loadSettlement(page){
  const s=await api('/api/counter/settlements');
  const sp=paginate(s.settlements||(),'sc',page);
  document.querySelector('#settleCounterTable tbody').innerHTML=sp.items.map(x=>`<tr><td>${escHtml(x.admin_username)}</td><td>${escHtml(x.settled_by)}</td><td>${x.amount_count}</td><td>${fmtDate(x.settled_at)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No settlements</td></tr>';
  document.getElementById('settleCounterPager').innerHTML=pagerHtml('sc',sp.total,sp.totalPages,'loadSettlement');
  const v=await api('/api/vcounter/settlements');
  const vp=paginate(v.settlements||(),'sv',page);
  document.querySelector('#settleVcTable tbody').innerHTML=vp.items.map(x=>`<tr><td>${escHtml(x.admin_username)}</td><td>${escHtml(x.settled_by)}</td><td>${fmt(x.amount_bytes)}</td><td>${fmtDate(x.settled_at)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No settlements</td></tr>';
  document.getElementById('settleVcPager').innerHTML=pagerHtml('sv',vp.total,vp.totalPages,'loadSettlement');
}

async function settleCounterFromPage(){
  const admin=document.getElementById('settleCounterAdmin').value.trim();
  if(!admin)return toast('Enter admin username','error');
  if(!confirm('Settle '+admin+'?'))return;
  const d=await api('/api/counter/settle',{method:'POST',body:JSON.stringify({admin_username:admin,settled_by:'web'})});
  if(d.error){toast(d.error,'error');return;}
  toast('Settled '+d.settled+' configs','success');
  loadSettlement();
}

async function settleVCounterFromPage(){
  const admin=document.getElementById('settleVcAdmin').value.trim();
  if(!admin)return toast('Enter admin username','error');
  if(!confirm('Settle '+admin+'?'))return;
  const d=await api('/api/vcounter/settle',{method:'POST',body:JSON.stringify({admin_username:admin,settled_by:'web'})});
  if(d.error){toast(d.error,'error');return;}
  toast('Settled '+fmt(d.settled)+' GB','success');
  loadSettlement();
}

// SERVICES
async function loadDaemonStatus(){
  const d=await api('/api/daemon/status');
  document.getElementById('daemonStatus').innerHTML=d.running?`<span class="badge badge-success">RUNNING</span> PID: ${d.pid}`:`<span class="badge badge-danger">STOPPED</span>`;
}
async function daemonStart(){
  const d=await api('/api/daemon/start',{method:'POST',body:JSON.stringify({})});
  if(d.error){toast(d.error,'error');return;}
  toast('Daemon started (PID '+d.pid+')','success');loadDaemonStatus();
}
async function daemonStop(){
  await api('/api/daemon/stop',{method:'POST',body:JSON.stringify({})});
  toast('Daemon stopped','success');loadDaemonStatus();
}
async function loadDaemonLogs(){
  const d=await api('/api/daemon/logs?lines=80');
  if(d.error)return;
  document.getElementById('daemonLogs').textContent=d.logs||'No logs yet.';
}

// WEB DAEMON
async function loadWebDaemonStatus(){
  const d=await api('/api/web/status');
  document.getElementById('webDaemonStatus').innerHTML=d.running?`<span class="badge badge-success">RUNNING</span> Port: ${d.port||'?'}`:`<span class="badge badge-danger">STOPPED</span>`;
}
async function webDaemonStart(){
  const d=await api('/api/web/start',{method:'POST',body:JSON.stringify({})});
  if(d.error){toast(d.error,'error');return;}
  toast('Web dashboard started','success');loadWebDaemonStatus();
}
async function webDaemonStop(){
  await api('/api/web/stop',{method:'POST',body:JSON.stringify({})});
  toast('Web dashboard stopped','success');loadWebDaemonStatus();
}
