/* BoutiqueGest - indicateur connexion + barre de statut type iTunes */
(function(){
  const bar = document.getElementById('sysBar');
  const conn = document.getElementById('sysConn');
  const txt = document.getElementById('sysText');
  const prog = document.getElementById('sysProg');
  const pct = document.getElementById('sysPct');

  function setConn(){
    if(!conn) return;
    if(navigator.onLine){
      conn.textContent = 'En ligne';
      conn.classList.remove('off');
      conn.classList.add('on');
    }else{
      conn.textContent = 'Hors ligne';
      conn.classList.remove('on');
      conn.classList.add('off');
    }
  }
  setConn();
  window.addEventListener('online', ()=>{setConn(); tryAutoBackup();});
  window.addEventListener('offline', setConn);

  function show(msg, p){
    if(!bar) return;
    if(txt) txt.textContent = msg;
    if(prog && pct){
      if(typeof p === 'number'){
        prog.style.display='flex';
        const val = Math.max(0, Math.min(100, p));
        prog.querySelector('.sys-bar-fill').style.width = val+'%';
        pct.textContent = Math.round(val)+'%';
      }else{
        prog.style.display='none';
      }
    }
    bar.classList.add('show');
  }
  function hide(){ if(bar){ bar.classList.remove('show'); }}

  async function fetchStatus(){
    try{
      const r = await fetch('/api/system/status', {cache:'no-store'});
      const d = await r.json();
      // petit indicateur
    }catch(e){}
  }

  let lastBackup = localStorage.getItem('bg_last_backup') || '';
  async function tryAutoBackup(){
    if(!navigator.onLine) return;
    const now = new Date();
    const today = now.toISOString().slice(0,10);
    if(lastBackup === today) return;
    try{
      show('Sauvegarde automatique en cours...', 10);
      const fd = new FormData();
      // csrf si présent
      const csrf = document.querySelector('input[name="csrf_token"]');
      if(csrf) fd.append('csrf_token', csrf.value);
      // tenter snapshot
      const r = await fetch('/admin/sauvegardes/historique/creer-ajax', {method:'POST', body: fd});
      if(r.ok){
        show('Sauvegarde automatique terminée', 100);
        localStorage.setItem('bg_last_backup', today);
        setTimeout(hide, 2500);
      }else{
        hide();
      }
    }catch(e){ hide(); }
  }

  setTimeout(tryAutoBackup, 2000);
  setInterval(fetchStatus, 60000);
  window.BoutiqueGestSys = { show, hide };
})();
