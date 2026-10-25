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

  var I18N = {
    en: { loading:'Loading shared PRD...', missing_h:'This PRD is not available', missing_p:'The link may have been unshared or removed.', missing_cta:'Create your own \u2192', eyebrow:'Shared PRD', tagline:'Generated in under a minute with PRD Studio.', cta:'Write your own PRD \u2192', foot:'PRD Studio \u00b7 AI product spec generator', nav_features:'Features', nav_pricing:'Pricing', nav_docs:'Docs', nav_terms:'Terms', nav_try:'Try free', side_doc:'Document', side_lang:'Language', lang_en:'English', lang_id:'Bahasa Indonesia', generating:'Generating', untitled:'Untitled', ask_h:'Ask this PRD', ask_p:'Answers come from the AI, grounded in this document only. Guests get a few questions per day.', ask_btn:'Ask', ask_ph:"Ask about this PRD, e.g. 'what is the riskiest part?'", ask_thinking:'Thinking...', ask_err:'Could not answer that. Please try again later.', ask_limit:'Daily limit reached — try again tomorrow.' },
    id: { loading:'Memuat PRD...', missing_h:'PRD ini tidak tersedia', missing_p:'Tautan mungkin sudah dibagikan ulang atau dihapus.', missing_cta:'Buat punyamu \u2192', eyebrow:'PRD Dibagikan', tagline:'Dibuat dalam waktu kurang dari satu menit dengan PRD Studio.', cta:'Tulis PRD kamu sendiri \u2192', foot:'PRD Studio \u00b7 Generator spesifikasi produk AI', nav_features:'Fitur', nav_pricing:'Harga', nav_docs:'Dokumentasi', nav_terms:'Ketentuan', nav_try:'Coba gratis', side_doc:'Dokumen', side_lang:'Bahasa', lang_en:'English', lang_id:'Bahasa Indonesia', generating:'Membuat', untitled:'Tanpa judul', ask_h:'Tanya PRD ini', ask_p:'Jawaban datang dari AI, berdasarkan dokumen ini saja. Tamu mendapat beberapa pertanyaan per hari.', ask_btn:'Tanya', ask_ph:"Tanya soal PRD ini, mis. 'bagian paling berisiko?'", ask_thinking:'Memikirkan...', ask_err:'Tidak bisa menjawab sekarang. Coba lagi nanti ya.', ask_limit:'Kuota harian habis — coba lagi besok.' }
  };
  var cur = 'en';
  function t(key){ var l = I18N[cur] || I18N.en; return l[key] || I18N.en[key] || key; }
  function applyI18n(){
    document.querySelectorAll('[data-i18n]').forEach(function(el){ el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){ el.placeholder = t(el.dataset.i18nPh); });
    if(document.documentElement) document.documentElement.lang = (cur === 'id' ? 'id' : 'en');
  }

  var m = location.pathname.match(/\/p\/([^\/?#]+)(?:\/([^\/?#]+))?/);
  var sid = m ? m[1] : '';
  var lang = (m && m[2]) ? m[2] : 'en';
  if(!sid){ cur = lang; $('loading').hidden=true; $('missing').hidden=false; applyI18n(); return; }

  var docMd = '';

  fetch('/api/shared/' + encodeURIComponent(sid))
    .then(function(r){ if(!r.ok) throw 0; return r.json(); })
    .then(function(d){
      $('loading').hidden = true;
      $('content').hidden = false;
      document.title = (d.name||'Shared PRD') + ' - PRD Studio';
      cur = d.lang || lang || 'en';
      applyI18n();
      $('title').textContent = d.name || t('untitled');
      $('meta').textContent = (d.template||'') + (d.created_at ? ' \u00b7 ' + d.created_at : '');
      docMd = d.markdown || '';
      $('doc').innerHTML = mdToHtml(docMd);
      $('askPanel').hidden = false;
      wireAsk();
      renderLangSwitch(docMd);
    })
    .catch(function(){ $('loading').hidden=true; $('missing').hidden=false; applyI18n(); });

  function bubble(cls, text){
    var el = document.createElement('div');
    el.className = 'ask-bubble ' + cls;
    el.style.cssText = cls === 'q'
      ? 'align-self:flex-end;background:var(--dark);color:#fff;padding:8px 12px;border-radius:12px 12px 2px 12px;max-width:85%;font-size:.92rem'
      : 'align-self:flex-start;background:var(--lightgray);color:var(--dark);padding:10px 12px;border-radius:12px 12px 12px 2px;max-width:90%;font-size:.92rem;white-space:pre-wrap';
    el.textContent = text;
    $('askLog').appendChild(el);
    el.scrollIntoView({behavior:'smooth', block:'end'});
    return el;
  }

  function wireAsk(){
    var btn = $('askBtn'), input = $('askInput');
    function ask(){
      var q = (input.value || '').trim();
      if(!q || btn.disabled) return;
      input.value = '';
      btn.disabled = true;
      bubble('q', q);
      var thinking = bubble('a', t('ask_thinking'));
      fetch('/api/chat', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ markdown: docMd, question: q })
      }).then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })
        .then(function(res){
          thinking.remove();
          if(!res.ok){
            bubble('a', (res.j && /limit/i.test(res.j.detail||'')) ? t('ask_limit') : t('ask_err'));
            return;
          }
          bubble('a', (res.j.answer || t('ask_err')).trim());
        })
        .catch(function(){ thinking.remove(); bubble('a', t('ask_err')); })
        .then(function(){ btn.disabled = false; input.focus(); });
    }
    btn.addEventListener('click', ask);
    input.addEventListener('keydown', function(e){ if(e.key === 'Enter') ask(); });
  }

  function renderLangSwitch(currentMd){
    var sw = $('langSwitch');
    if(!sw) return;
    sw.innerHTML =
      '<button class="tpl' + (cur==='en'?' on':'') + '" style="text-align:left" data-lang="en">' + t('lang_en') + '</button>' +
      '<button class="tpl' + (cur==='id'?' on':'') + '" style="text-align:left" data-lang="id">' + t('lang_id') + '</button>';
    sw.querySelectorAll('[data-lang]').forEach(function(b){
      b.addEventListener('click', function(){
        var target = b.dataset.lang;
        if(target === cur) return;
        sw.querySelectorAll('[data-lang]').forEach(function(x){ x.disabled = true; });
        var status = document.createElement('span');
        status.style.cssText = 'font-family:Poppins,sans-serif;font-size:.76rem;color:#8a8880;margin-top:4px';
        status.textContent = t('generating') + ' ' + (target==='id'?t('lang_id'):t('lang_en')) + '...';
        sw.appendChild(status);
        fetch('/api/shared/' + encodeURIComponent(sid) + '/translate',{
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({lang: target})
        }).then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })
          .then(function(res){
            if(!res.ok){ status.textContent = (res.j && res.j.detail) || 'Could not switch language.'; return; }
            cur = target;
            docMd = res.j.markdown || '';
            $('doc').innerHTML = mdToHtml(docMd);
            renderLangSwitch(docMd);
          })
          .catch(function(){ status.textContent = 'Could not reach the service.'; });
      });
    });
  }
})();
