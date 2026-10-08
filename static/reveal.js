(function(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // scroll reveal
  var sel = 'section .center, .feat, .step, .panel, .trial, .endpoint, .ep, .docs > div, .docc > section, .stats';
  var els = document.querySelectorAll(sel);
  els.forEach(function(el){ el.classList.add('reveal'); });
  ['feat','step','endpoint','ep'].forEach(function(cls){
    document.querySelectorAll('.'+cls).forEach(function(el,i){ el.classList.add('d'+((i%5)+1)); });
  });

  if(reduce || !('IntersectionObserver' in window)){
    els.forEach(function(el){ el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } });
    }, {threshold:.12, rootMargin:'0px 0px -8% 0px'});
    els.forEach(function(el){ io.observe(el); });
  }

  // nav: hide on scroll down, show on scroll up, shadow when scrolled
  var nav = document.querySelector('nav');
  if(nav){
    var last = window.scrollY;
    window.addEventListener('scroll', function(){
      var y = window.scrollY;
      nav.classList.toggle('scrolled', y > 8);
      if(y > last && y > 160) nav.classList.add('nav-up');
      else nav.classList.remove('nav-up');
      last = y;
    }, {passive:true});
  }
})();