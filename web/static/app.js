const GB=1024*1024*1024;
let currentPage='dashboard';

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
    vcounter:loadVCounter,
    iplimit:loadIpLimits,
    volume:()=>{loadExempt();loadVolumeNotifs();loadVolumeConfig();},
    users:loadUsers,
    subadmin:()=>{loadCounterSubAdmins();loadVCounterSubAdmins();},
    telegram:()=>{},
    settings:loadSettings,
    daemon:()=>{loadDaemonStatus();loadDaemonLogs();},
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

// DASHBOARD
async function loadDashboard(){
  const d=await api('/api/summary');
  if(d.error)return;
  const el=document.getElementById('summaryCards');
  el.innerHTML=`
    <div class="stat-card"><div class="stat-label">Total Users</div><div class="stat-value primary">${d.total_users}</div></div>
    <div class="stat-card"><div class="stat-label">Active Users</div><div class="stat-value success">${d.active_users}</div></div>
    <div class="stat-card"><div class="stat-label">Admins</div><div class="stat-value info">${d.admin_count}</div></div>
    <div class="stat-card"><div class="stat-label">Exempt</div><div class="stat-value warning">${d.exempt_count}</div></div>
  `;
  const tb=document.querySelector('#adminTable tbody');
  const allAdmins=new Set();
  (d.counter_totals||[]).forEach(c=>allAdmins.add(c.admin_username));
  (d.vcounter_totals||[]).forEach(v=>allAdmins.add(v.admin_username));
  Object.keys(d.admins||{}).forEach(a=>allAdmins.add(a));
  const rows=[];
  allAdmins.forEach(a=>{
    const ct=(d.counter_totals||[]).find(c=>c.admin_username===a);
    const vt=(d.vcounter_totals||[]).find(v=>v.admin_username===a);
    rows.push(`<tr><td>${a}</td><td>${d.admins[a]||'-'}</td><td>${ct?ct.total_count:'-'}</td><td>${vt?fmt(vt.total_volume_bytes):'-'}</td></tr>`);
  });
  tb.innerHTML=rows.join('')||'<tr><td colspan="4" class="empty">No data</td></tr>';
}

// COUNTER
async function loadCounter(){
  const d=await api('/api/counter/report?viewer=web');
  if(d.error)return;
  const el=document.getElementById('counterCards');
  el.innerHTML=`
    <div class="stat-card"><div class="stat-label">Total Count</div><div class="stat-value primary">${d.total}</div></div>
    <div class="stat-card"><div class="stat-label">Admins</div><div class="stat-value info">${d.admins.length}</div></div>
  `;
  const tb=document.querySelector('#counterTable tbody');
  tb.innerHTML=d.admins.map(a=>`
    <tr>
      <td>${a.admin_username}</td>
      <td><strong>${a.total_count}</strong></td>
      <td><button class="btn btn-sm btn-primary" onclick="settleCounter('${a.admin_username}')">Settle</button></td>
    </tr>
  `).join('')||'<tr><td colspan="3" class="empty">No data</td></tr>';
  const s=await api('/api/counter/settlements');
  const stb=document.querySelector('#counterSettlements tbody');
  stb.innerHTML=(s.settlements||[]).slice(0,20).map(x=>`
    <tr><td>${x.admin_username}</td><td>${x.settled_by}</td><td>${x.amount_count}</td><td>${fmtDate(x.settled_at)}</td></tr>
  `).join('')||'<tr><td colspan="4" class="empty">No settlements</td></tr>';
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
async function loadVCounter(){
  const d=await api('/api/vcounter/report?viewer=web');
  if(d.error)return;
  const el=document.getElementById('vcounterCards');
  el.innerHTML=`
    <div class="stat-card"><div class="stat-label">Total Volume</div><div class="stat-value primary">${fmt(d.total_bytes)} GB</div></div>
    <div class="stat-card"><div class="stat-label">Admins</div><div class="stat-value info">${d.admins.length}</div></div>
  `;
  const tb=document.querySelector('#vcounterTable tbody');
  tb.innerHTML=d.admins.map(a=>`
    <tr>
      <td>${a.admin_username}</td>
      <td><strong>${fmt(a.total_volume_bytes)} GB</strong></td>
      <td><button class="btn btn-sm btn-primary" onclick="settleVCounter('${a.admin_username}')">Settle</button></td>
    </tr>
  `).join('')||'<tr><td colspan="3" class="empty">No data</td></tr>';
  const s=await api('/api/vcounter/settlements');
  const stb=document.querySelector('#vcounterSettlements tbody');
  stb.innerHTML=(s.settlements||[]).slice(0,20).map(x=>`
    <tr><td>${x.admin_username}</td><td>${x.settled_by}</td><td>${fmt(x.amount_bytes)}</td><td>${fmtDate(x.settled_at)}</td></tr>
  `).join('')||'<tr><td colspan="4" class="empty">No settlements</td></tr>';
}

async function settleVCounter(admin){
  if(!confirm('Settle '+admin+'?'))return;
  const d=await api('/api/vcounter/settle',{method:'POST',body:JSON.stringify({admin_username:admin,settled_by:'web'})});
  if(d.error){toast(d.error,'error');return;}
  toast('Settled '+fmt(d.settled)+' GB','success');
  loadVCounter();
}

// IP LIMIT
async function loadIpLimits(){
  const d=await api('/api/ip/limits');
  if(d.error)return;
  const tb=document.querySelector('#ipTable tbody');
  const limits=d.limits||{};
  tb.innerHTML=Object.entries(limits).map(([u,l])=>`
    <tr><td>${u}</td><td>${l}</td></tr>
  `).join('')||'<tr><td colspan="2" class="empty">No limits set</td></tr>';
}

async function setIpLimit(){
  const u=document.getElementById('ipUsername').value.trim();
  const l=document.getElementById('ipLimit').value;
  if(!u)return toast('Enter username','error');
  await api('/api/ip/set',{method:'POST',body:JSON.stringify({username:u,limit:parseInt(l)})});
  toast('IP limit set','success');
  loadIpLimits();
}

async function deleteIpLimit(){
  const u=document.getElementById('ipUsername').value.trim();
  if(!u)return toast('Enter username','error');
  await api('/api/ip/delete',{method:'POST',body:JSON.stringify({username:u})});
  toast('IP limit removed','success');
  loadIpLimits();
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

async function loadExempt(){
  const d=await api('/api/volume/exempt');
  if(d.error)return;
  const tb=document.querySelector('#exemptTable tbody');
  tb.innerHTML=(d.exempt||[]).map(e=>`
    <tr><td>${e.username}</td><td>${fmtDate(e.added_at)}</td></tr>
  `).join('')||'<tr><td colspan="2" class="empty">No exempt users</td></tr>';
}

async function addExempt(){
  const u=document.getElementById('exemptUsername').value.trim();
  if(!u)return toast('Enter username','error');
  await api('/api/volume/exempt/add',{method:'POST',body:JSON.stringify({username:u})});
  toast('User exempted','success');
  document.getElementById('exemptUsername').value='';
  loadExempt();
}

async function removeExempt(){
  const u=document.getElementById('exemptUsername').value.trim();
  if(!u)return toast('Enter username','error');
  await api('/api/volume/exempt/remove',{method:'POST',body:JSON.stringify({username:u})});
  toast('User removed from exempt','success');
  loadExempt();
}

async function loadVolumeNotifs(){
  const d=await api('/api/volume/notifications');
  if(d.error)return;
  const tb=document.querySelector('#volNotifTable tbody');
  tb.innerHTML=(d.notifications||[]).map(n=>`
    <tr><td>${n.username}</td><td>${n.admin_username||'-'}</td><td>${fmt(n.used_traffic_bytes)}</td><td>${fmtDate(n.disabled_at)}</td></tr>
  `).join('')||'<tr><td colspan="4" class="empty">No disabled users</td></tr>';
}

// USERS
async function loadUsers(){
  const d=await api('/api/users');
  if(d.error){toast('Not connected to panel','error');return;}
  const tb=document.querySelector('#usersTable tbody');
  tb.innerHTML=(d.users||[]).map(u=>`
    <tr>
      <td>${u.username}</td>
      <td><span class="badge badge-${u.status==='active'?'success':'danger'}">${u.status}</span></td>
      <td>${u.admin}</td>
      <td>${u.data_limit?fmt(u.data_limit)+' GB':'Unlimited'}</td>
      <td>${fmt(u.used_traffic)} GB</td>
      <td>${fmtDate(u.created_at)}</td>
    </tr>
  `).join('')||'<tr><td colspan="6" class="empty">No users</td></tr>';
}

// SUB-ADMINS
async function loadCounterSubAdmins(){
  const d=await api('/api/subadmin/counter');
  if(d.error)return;
  const tb=document.querySelector('#saCounterTable tbody');
  tb.innerHTML=(d.sub_admins||[]).map(s=>`
    <tr><td>${s.telegram_id}</td><td>${s.allowed_admins}</td></tr>
  `).join('')||'<tr><td colspan="2" class="empty">No sub-admins</td></tr>';
}

async function addCounterSubAdmin(){
  const tid=document.getElementById('saTgId').value.trim();
  const admins=document.getElementById('saAdmins').value.trim().split(',').map(s=>s.trim()).filter(Boolean);
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/counter/add',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid),allowed_admins:admins})});
  toast('Sub-admin added','success');
  loadCounterSubAdmins();
}

async function removeCounterSubAdmin(){
  const tid=document.getElementById('saTgId').value.trim();
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/counter/remove',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid)})});
  toast('Sub-admin removed','success');
  loadCounterSubAdmins();
}

async function loadVCounterSubAdmins(){
  const d=await api('/api/subadmin/vcounter');
  if(d.error)return;
  const tb=document.querySelector('#saVCounterTable tbody');
  tb.innerHTML=(d.sub_admins||[]).map(s=>`
    <tr><td>${s.telegram_id}</td><td>${s.allowed_admins}</td></tr>
  `).join('')||'<tr><td colspan="2" class="empty">No sub-admins</td></tr>';
}

async function addVCounterSubAdmin(){
  const tid=document.getElementById('vcSaTgId').value.trim();
  const admins=document.getElementById('vcSaAdmins').value.trim().split(',').map(s=>s.trim()).filter(Boolean);
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/vcounter/add',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid),allowed_admins:admins})});
  toast('Sub-admin added','success');
  loadVCounterSubAdmins();
}

async function removeVCounterSubAdmin(){
  const tid=document.getElementById('vcSaTgId').value.trim();
  if(!tid)return toast('Enter Telegram ID','error');
  await api('/api/subadmin/vcounter/remove',{method:'POST',body:JSON.stringify({telegram_id:parseInt(tid)})});
  toast('Sub-admin removed','success');
  loadVCounterSubAdmins();
}

// TELEGRAM
async function testTelegram(){
  document.getElementById('tgResult').innerHTML='<p>Testing...</p>';
  const d=await api('/api/telegram/test',{method:'POST',body:JSON.stringify({})});
  document.getElementById('tgResult').innerHTML=d.ok
    ?`<p style="color:var(--success)">${d.message}</p>`
    :`<p style="color:var(--danger)">${d.message}</p>`;
}

// SETTINGS
async function loadSettings(){
  const d=await api('/api/settings');
  if(d.error)return;
  document.getElementById('setUrl').value=d.server_url||'';
  document.getElementById('setUser').value=d.username||'';
  document.getElementById('setFlowVal').value=d.flow_value||'xtls-rprx-vision';
  document.getElementById('setFlow').checked=d.flow_enabled;
  document.getElementById('setIp').checked=d.ip_limit_enabled;
  document.getElementById('setIpAll').value=d.ip_limit_all||1;
  document.getElementById('setCounter').checked=d.counter_enabled;
  document.getElementById('setVcounter').checked=d.vcounter_enabled;
  document.getElementById('setVol').checked=d.volume_limit_enabled;
  document.getElementById('setVolGb').value=d.volume_limit_gb||250;
  document.getElementById('setTg').checked=d.telegram_enabled;
  document.getElementById('setTgToken').value=d.telegram_token||'';
  document.getElementById('setTgAdmin').value=d.telegram_admin_id||'';
  document.getElementById('setInterval').value=d.daemon_interval||20;
  document.getElementById('setBanTime').value=d.ban_time||4;
  document.getElementById('setSshPort').value=d.ssh_port||22;
}

async function saveSettings(){
  const pass=document.getElementById('setPass').value;
  const data={
    server_url:document.getElementById('setUrl').value,
    username:document.getElementById('setUser').value,
    flow_value:document.getElementById('setFlowVal').value,
    flow_enabled:document.getElementById('setFlow').checked,
    ip_limit_enabled:document.getElementById('setIp').checked,
    ip_limit_all:parseInt(document.getElementById('setIpAll').value),
    counter_enabled:document.getElementById('setCounter').checked,
    vcounter_enabled:document.getElementById('setVcounter').checked,
    volume_limit_enabled:document.getElementById('setVol').checked,
    volume_limit_gb:parseInt(document.getElementById('setVolGb').value),
    telegram_enabled:document.getElementById('setTg').checked,
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

// DAEMON
async function loadDaemonStatus(){
  const d=await api('/api/daemon/status');
  const el=document.getElementById('daemonStatus');
  if(d.running){
    el.innerHTML=`<span class="badge badge-success">RUNNING</span> PID: ${d.pid}`;
  }else{
    el.innerHTML=`<span class="badge badge-danger">STOPPED</span>`;
  }
}

async function daemonStart(){
  const d=await api('/api/daemon/start',{method:'POST',body:JSON.stringify({})});
  if(d.error){toast(d.error,'error');return;}
  toast('Daemon started (PID '+d.pid+')','success');
  loadDaemonStatus();
}

async function daemonStop(){
  await api('/api/daemon/stop',{method:'POST',body:JSON.stringify({})});
  toast('Daemon stopped','success');
  loadDaemonStatus();
}

async function loadDaemonLogs(){
  const d=await api('/api/daemon/logs?lines=60');
  if(d.error)return;
  document.getElementById('daemonLogs').textContent=d.logs||'No logs yet.';
}
