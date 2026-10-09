(function(){
  var KEY = 'prd_cookie_consent';
  try { if(localStorage.getItem(KEY)) return; } catch(e){}

  var css = '' +
    '.ck{position:fixed;left:16px;right:16px;bottom:16px;z-index:200;max-width:920px;margin:0 auto;' +
    'background:var(--dark);color:var(--light);border-radius:16px;padding:18px 20px;display:flex;gap:18px;' +
    'align-items:center;justify-content:space-between;flex-wrap:wrap;box-shadow:0 24px 60px -24px rgba(20,20,19,.6);' +
    'transform:translateY(140%);transition:transform .5s cubic-bezier(.22,.7,.24,1);font-family:var(--sans,\'Poppins\',sans-serif)}' +
    '.ck.show{transform:none}' +
    '.ck p{margin:0;font-size:.88rem;line-height:1.5;color:#e8e6dc;max-width:600px}' +
    '.ck a{color:var(--orange)}' +
    '.ck .btns{display:flex;gap:10px;flex-shrink:0}' +
    '.ck button{border:none;border-radius:999px;padding:10px 20px;font-family:inherit;font-size:.85rem;font-weight:600;cursor:pointer;transition:.2s}' +
    '.ck .acc{background:var(--orange);color:#fff}.ck .acc:hover{background:#c96848}' +
    '.ck .dec{background:transparent;color:var(--light);border:1px solid rgba(250,249,245,.35)}.ck .dec:hover{background:rgba(250,249,245,.12)}' +
    '@media(max-width:600px){.ck{flex-direction:column;align-items:stretch;text-align:left}.ck .btns{justify-content:flex-end}}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  var bar = document.createElement('div');
  bar.className = 'ck';
  bar.setAttribute('role','dialog');
  bar.setAttribute('aria-label','Cookie consent');
  bar.innerHTML =
    '<p>We use essential cookies to keep you signed in and remember your preferences. ' +
    'No tracking or advertising cookies. Read our <a href="/terms">terms</a>.</p>' +
    '<div class="btns">' +
    '<button class="dec" type="button">Decline</button>' +
    '<button class="acc" type="button">Accept</button>' +
    '</div>';
  document.body.appendChild(bar);
  requestAnimationFrame(function(){ setTimeout(function(){ bar.classList.add('show'); }, 300); });

  function done(v){ try{ localStorage.setItem(KEY, v); }catch(e){} bar.classList.remove('show'); setTimeout(function(){ bar.remove(); }, 500); }
  bar.querySelector('.acc').addEventListener('click', function(){ done('accept'); });
  bar.querySelector('.dec').addEventListener('click', function(){ done('decline'); });
})();
