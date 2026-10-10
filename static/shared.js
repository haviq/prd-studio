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
      var dl = (d.lang || lang || 'en');
      var sw = $('langSwitch');
      if(sw) sw.innerHTML = '<span style="font-family:Poppins,sans-serif;font-size:.82rem;color:#8a8880">Document language: <strong style="color:#141413">' + (dl === 'id' ? 'Bahasa Indonesia' : 'English') + '</strong></span>';
      $('doc').innerHTML = mdToHtml(d.markdown || '');
    })
    .catch(function(){ $('loading').hidden=true; $('missing').hidden=false; });
})();
