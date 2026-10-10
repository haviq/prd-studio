(function(){
  var $ = function(id){ return document.getElementById(id); };
  function setStatus(msg, err){ var s=$('status'); if(s){ s.className='status'+(err?' err':''); s.textContent=msg||''; } }

  var method = 'qris';
  document.querySelectorAll('#methods .tpl').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('#methods .tpl').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on'); method = b.dataset.m;
    });
  });

  fetch('/api/me').then(function(r){return r.json();}).then(function(me){
    if(me.logged_in){ $('payBox').hidden = false; if(me.plan==='pro'){ $('payBox').hidden=true; $('alreadyPro').hidden=false; } }
    else { $('notLoggedIn').hidden = false; }
  }).catch(function(){ $('notLoggedIn').hidden = false; });

  var order = '';
  function poll(){
    if(!order) return;
    fetch('/api/checkout/status/' + order).then(function(r){return r.json();}).then(function(j){
      if(j.status === 'paid'){ $('payBox').hidden=true; $('doneBox').hidden=false; setStatus('Payment received. You are Pro.'); return; }
      setTimeout(poll, 4000);
    }).catch(function(){ setTimeout(poll, 5000); });
  }

  var payBtn = $('payBtn');
  if(payBtn) payBtn.addEventListener('click', function(){
    payBtn.disabled = true; setStatus('Creating payment...');
    fetch('/api/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:'pro', method:method})})
      .then(function(r){return r.json();})
      .then(function(j){
        if(!j.pay_url){ setStatus(j.detail||'Could not start checkout.',true); payBtn.disabled=false; return; }
        order = j.order;
        if(j.configured === false){ setStatus(j.detail||'Payment gateway not configured yet.', true); }
        else { setStatus('Redirecting to payment...'); }
        window.location.href = j.pay_url;
        setTimeout(poll, 3000);
      })
      .catch(function(){ setStatus('Checkout failed.',true); payBtn.disabled=false; });
  });

  // resume polling if we came back with ?order=
  var q = location.search.match(/order=([^&]+)/);
  if(q){ order = decodeURIComponent(q[1]); poll(); }
})();
