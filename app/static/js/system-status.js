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
  window.addEventListener('online', setConn);
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

  setInterval(fetchStatus, 60000);
  window.BoutiqueGestSys = { show, hide };
})();
