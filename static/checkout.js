(function(){
  var $ = function(id){ return document.getElementById(id); };
  function setStatus(msg, err){ var s=$('status'); if(s){ s.className='status'+(err?' err':''); s.textContent=msg||''; } }

  fetch('/api/me').then(function(r){return r.json();}).then(function(me){
    if(me.logged_in){ $('payBox').hidden = false; }
    else { $('notLoggedIn').hidden = false; }
  }).catch(function(){ $('notLoggedIn').hidden = false; });

  $('payBtn').addEventListener('click', function(){
    $('payBtn').disabled = true; setStatus('Processing...');
    fetch('/api/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:'pro'})})
      .then(function(r){return r.json();})
      .then(function(j){
        if(!j.order){ setStatus(j.detail||'Could not start checkout.',true); $('payBtn').disabled=false; return; }
        return fetch('/api/checkout/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order:j.order})})
          .then(function(r){return r.json();})
          .then(function(c){
            $('payBox').hidden = true; $('doneBox').hidden = false;
            setStatus(c.message||'Upgraded.');
          });
      })
      .catch(function(){ setStatus('Checkout failed.',true); $('payBtn').disabled=false; });
  });
})();
