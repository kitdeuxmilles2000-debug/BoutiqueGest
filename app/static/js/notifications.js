<script>
(function(){
  var BADGE = document.querySelector('.notif-badge');
  var LIST = document.querySelector('.notif-dropdown-list');
  var DROPDOWN = document.querySelector('.notif-dropdown');
  var BELL = document.querySelector('.notif-bell');
  var BOX = document.getElementById('notifBox');
  var MARK_ALL = document.getElementById('notifMarkAll');
  var seen = {};
  var pollTimer = null;
  var audioCtx = null;

  /* ---------------- Bip sonore (Web Audio) ---------------- */
  function getAudioCtx(){
    if(!audioCtx){
      var Ctor = window.AudioContext || window.webkitAudioContext;
      if(!Ctor) return null;
      audioCtx = new Ctor();
    }
    return audioCtx;
  }
  function beep(){
    var ctx = getAudioCtx();
    if(!ctx) return;
    try{
      if(ctx.state === 'suspended') ctx.resume();
      var notes = [880, 1174.66];
      notes.forEach(function(freq, i){
        var t0 = ctx.currentTime + i * 0.14;
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.16);
        osc.start(t0);
        osc.stop(t0 + 0.2);
      });
    }catch(e){}
  }

  /* ---------------- Actions API ---------------- */
  async function apiMarkRead(id){
    try{
      var r = await fetch('/notifications/' + id + '/lire', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
      });
      return r.ok;
    }catch(e){ return false; }
  }
  async function apiMarkAllRead(){
    try{
      var r = await fetch('/notifications/lire-tout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
      });
      return r.ok;
    }catch(e){ return false; }
  }

  /* ---------------- Toasts ---------------- */
  function toast(it){
    if(!BOX) return null;
    var el = document.createElement('div');
    el.className = 'notif-toast';
    var t = document.createElement('div');
    t.className = 't';
    t.textContent = it.title || '';
    var m = document.createElement('div');
    m.className = 'm';
    m.textContent = it.message || '';
    el.appendChild(t);
    el.appendChild(m);
    el.addEventListener('click', function(){
      var link = it.link || '/notifications/';
      apiMarkRead(it.id).then(function(){ window.location.href = link; });
    });
    BOX.appendChild(el);
    setTimeout(function(){ if(el.parentNode){ el.parentNode.removeChild(el); } }, 6000);
    return el;
  }

  /* ---------------- Rendu de la liste (dropdown) ---------------- */
  function renderList(items){
    if(!LIST) return;
    LIST.innerHTML = '';
    var list = items || [];
    if(list.length === 0){
      var empty = document.createElement('div');
      empty.className = 'notif-empty';
      empty.textContent = 'Aucune alerte';
      LIST.appendChild(empty);
      return;
    }
    list.forEach(function(it){
      var a = document.createElement('a');
      a.className = 'notif-dd-item' + (it.read ? '' : ' unread');
      a.href = it.link || '/notifications/';
      a.addEventListener('click', function(ev){
        ev.preventDefault();
        apiMarkRead(it.id).then(function(){ window.location.href = it.link || '/notifications/'; });
      });
      var top = document.createElement('div');
      var t = document.createElement('div');
      t.className = 't';
      t.textContent = it.title || '';
      var m = document.createElement('div');
      m.className = 'm';
      m.textContent = (it.message || '').substring(0, 140);
      top.appendChild(t);
      top.appendChild(m);
      var meta = document.createElement('div');
      var d = document.createElement('div');
      d.className = 'd';
      var parts = [];
      if(it.label) parts.push(it.label);
      if(it.created_at) parts.push(new Date(it.created_at).toLocaleString('fr-FR'));
      d.textContent = parts.join(' · ');
      meta.appendChild(d);
      a.appendChild(top);
      a.appendChild(meta);
      LIST.appendChild(a);
    });
  }

  /* ---------------- Rafraîchissement ---------------- */
  async function refresh(){
    try{
      var res = await fetch('/notifications/api/list');
      if(!res.ok) return;
      var data = await res.json();
      var items = data.items || [];
      var unread = data.count || 0;
      if(BADGE){
        BADGE.textContent = unread;
        BADGE.style.display = unread > 0 ? 'inline-flex' : 'none';
      }
      var fresh = [];
      items.forEach(function(it){
        if(!it.read && !seen[it.id]){
          seen[it.id] = true;
          fresh.push(it);
        }
      });
      if(fresh.length > 0){
        fresh.forEach(function(it){ toast(it); });
        beep();
      }
      renderList(items);
    }catch(e){}
  }

  async function markAll(){
    var ok = await apiMarkAllRead();
    if(ok) await refresh();
  }

  /* ---------------- Polling + cycle de vie ---------------- */
  function schedulePoll(){
    if(pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(function(){ refresh(); }, 15000);
  }

  if(MARK_ALL){
    MARK_ALL.addEventListener('click', function(ev){
      ev.preventDefault();
      markAll();
    });
  }

  if(Bell){
    Bell.addEventListener('click', function(ev){
      ev.stopPropagation();
      var open = DROPDOWN ? DROPDOWN.classList.contains('open') : false;
      if(DROPDOWN) DROPDOWN.classList.toggle('open');
      if(!open){
        refresh();
      }
    });
  }
  document.addEventListener('click', function(ev){
    if(DROPDOWN && !DROPDOWN.contains(ev.target) && !(BELL && BELL.contains(ev.target))){
      DROPDOWN.classList.remove('open');
    }
  });
  document.addEventListener('keydown', function(ev){
    if(ev.key === 'Escape' && DROPDOWN) DROPDOWN.classList.remove('open');
  });

  refresh().then(function(){ schedulePoll(); });
})();
</script>
