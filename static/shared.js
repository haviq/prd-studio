(function(){
  var $ = function(id){ return document.getElementById(id); };

  function inlineMd(s){
    s=s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
    s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    s=s.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g,'$1<em>$2</em>');
    return s;
  }
  function mdToHtml(md){
    var lines=(md||'').split('\n'), out='', list=null;
    var close=function(){ if(list){ out+='</'+list+'>'; list=null; } };
    for(var i=0;i<lines.length;i++){
      var l=lines[i], t=l.trim();
      var mOl=t.match(/^(\d+)[.)]\s+(.*)$/);
      if(/^###\s+/.test(l)){ close(); out+='<h3>'+inlineMd(l.replace(/^###\s+/,''))+'</h3>'; }
      else if(/^##\s+/.test(l)){ close(); out+='<h2>'+inlineMd(l.replace(/^##\s+/,''))+'</h2>'; }
      else if(/^#\s+/.test(l)){ close(); out+='<h2>'+inlineMd(l.replace(/^#\s+/,''))+'</h2>'; }
      else if(/^[-*]\s+/.test(l)){ if(list!=='ul'){ close(); out+='<ul>'; list='ul'; } out+='<li>'+inlineMd(l.replace(/^[-*]\s+/,''))+'</li>'; }
      else if(mOl){ if(list!=='ol'){ close(); out+='<ol>'; list='ol'; } out+='<li>'+inlineMd(mOl[2])+'</li>'; }
      else if(t===''){ close(); }
      else { close(); out+='<p>'+inlineMd(l)+'</p>'; }
    }
    close();
    return out;
  }

  var m = location.pathname.match(/\/p\/([^\/?#]+)(?:\/([^\/?#]+))?/);
  var sid = m ? m[1] : '';
  var lang = (m && m[2]) ? m[2] : 'en';
  if(!sid){ $('loading').hidden=true; $('missing').hidden=false; return; }

  fetch('/api/shared/' + encodeURIComponent(sid))
    .then(function(r){ if(!r.ok) throw 0; return r.json(); })
    .then(function(d){
      $('loading').hidden = true;
      $('content').hidden = false;
      document.title = (d.name||'Shared PRD') + ' - PRD Studio';
      $('title').textContent = d.name || 'Untitled';
      $('meta').textContent = (d.template||'') + (d.created_at ? ' \u00b7 ' + d.created_at : '');
      cur = d.lang || lang || 'en';
      $('doc').innerHTML = mdToHtml(d.markdown || '');
      renderLangSwitch(d.markdown);
    })
    .catch(function(){ $('loading').hidden=true; $('missing').hidden=false; });

  var cur = 'en';
  function renderLangSwitch(currentMd){
    var sw = $('langSwitch');
    if(!sw) return;
    sw.innerHTML =
      '<span style="font-family:Poppins,sans-serif;font-size:.8rem;color:#8a8880;margin-right:10px">Language:</span>' +
      '<button class="tpl' + (cur==='en'?' on':'') + '" data-lang="en">English</button>' +
      '<button class="tpl' + (cur==='id'?' on':'') + '" data-lang="id">Bahasa Indonesia</button>';
    sw.querySelectorAll('[data-lang]').forEach(function(b){
      b.addEventListener('click', function(){
        var target = b.dataset.lang;
        if(target === cur) return;
        sw.querySelectorAll('[data-lang]').forEach(function(x){ x.disabled = true; });
        var status = document.createElement('span');
        status.style.cssText = 'font-family:Poppins,sans-serif;font-size:.8rem;color:#8a8880;margin-left:10px';
        status.textContent = 'Generating ' + (target==='id'?'Bahasa Indonesia':'English') + '... (up to ~60s)';
        sw.appendChild(status);
        fetch('/api/shared/' + encodeURIComponent(sid) + '/translate',{
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({lang: target})
        }).then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })
          .then(function(res){
            if(!res.ok){ status.textContent = (res.j && res.j.detail) || 'Could not switch language.'; return; }
            cur = target;
            $('doc').innerHTML = mdToHtml(res.j.markdown || '');
            renderLangSwitch(res.j.markdown);
          })
          .catch(function(){ status.textContent = 'Could not reach the service.'; });
      });
    });
  }
})();
