// PRD Studio i18n - lightweight UI translation (EN/ID).
// Translates text nodes and placeholders via an exact-match phrase map,
// plus optional data-i18n keys. Language persists in localStorage.
(function(){
  var DICT = {
    id: {
      // nav
      "Features":"Fitur", "Pricing":"Harga", "Docs":"Dokumentasi", "Gallery":"Galeri",
      "Roadmap":"Peta Jalan", "Status":"Status", "Home":"Beranda", "Terms":"Ketentuan",
      "Try free":"Coba gratis", "Try the studio":"Coba studio", "Back to home":"Kembali ke beranda",
      "Sign in":"Masuk", "Sign out":"Keluar", "Create account":"Buat akun", "Continue as guest":"Lanjut sebagai tamu",
      "Continue with GitHub":"Lanjut dengan GitHub", "Sign in with GitHub":"Masuk dengan GitHub",
      "Welcome back":"Selamat datang kembali", "Sign in to keep building your PRDs.":"Masuk untuk lanjut membangun PRD kamu.",
      "or":"atau", "Name":"Nama", "Email":"Email", "Password":"Kata sandi",
      "Your name":"Nama kamu", "At least 6 characters":"Minimal 6 karakter",
      "By continuing you agree to our":"Dengan melanjutkan kamu setuju dengan", "terms":"ketentuan", "privacy policy":"kebijakan privasi",
      "and":"dan",
      // studio
      "Studio":"Studio", "Workspace":"Ruang kerja", "Output":"Hasil",
      "Product type":"Jenis produk", "Output language":"Bahasa hasil", "App name":"Nama aplikasi",
      "Describe it":"Jelaskan", "Who and how":"Siapa dan bagaimana",
      "Description":"Deskripsi", "Main features":"Fitur utama", "Target users":"Target pengguna", "Tech stack":"Teknologi",
      "Next":"Lanjut", "Back":"Kembali", "Generate PRD & diagrams":"Buat PRD & diagram",
      "Full pack (PRD + Spec + Stories)":"Paket lengkap (PRD + Spesifikasi + User Story)",
      "Suggest fields with AI":"Saran field dengan AI", "Import brief":"Impor brief",
      "Paste your brief (from Notion, Docs, anywhere)":"Tempel brief kamu (dari Notion, Docs, dsb)",
      "Fill the form":"Isi formulir",
      "Save":"Simpan", "Share link":"Bagikan tautan", "Save version":"Simpan versi", "History":"Riwayat",
      "Copy":"Salin", "Tickets":"Tiket", "Review":"Tinjau", "Estimate":"Estimasi",
      "Ask about this PRD, e.g. 'what is the riskiest part?'":"Tanya soal PRD ini, mis. 'bagian paling berisiko?'", "Ask":"Tanya",
      "Write your PRD in three steps.":"Tulis PRD kamu dalam tiga langkah.",
      "What are you building?":"Kamu membangun apa?", "Pick a type and name your product. AI can fill the rest.":"Pilih jenis dan beri nama produkmu. AI bisa mengisi sisanya.",
      "One or two sentences. Click a suggestion to fill a field.":"Satu dua kalimat. Klik saran untuk mengisi field.",
      "Optional, but it sharpens the output.":"Opsional, tapi menajamkan hasil.",
      "Version history":"Riwayat versi", "Close":"Tutup", "Restore":"Pulihkan",
      // account
      "Plan":"Paket", "Usage":"Penggunaan", "Saved projects":"Proyek tersimpan", "Teams":"Tim",
      "Settings":"Pengaturan", "AI provider":"Provider AI", "Account":"Akun",
      "PRDs generated":"PRD dibuat", "Revisions":"Revisi", "Today":"Hari ini",
      "Recent activity":"Aktivitas terbaru", "Upgrade to Pro":"Upgrade ke Pro",
      "Create team":"Buat tim", "Team name":"Nama tim", "Open":"Buka", "Delete":"Hapus", "Share":"Bagikan",
      // pricing
      "Free":"Gratis", "Enterprise":"Enterprise", "Start free":"Mulai gratis", "Go Pro":"Go Pro",
      "Contact sales":"Hubungi sales", "Compare all plans":"Bandingkan semua paket", "Most popular":"Paling populer",
      "Start free. Upgrade when you need more.":"Mulai gratis. Upgrade kalau butuh lebih.",
      // landing
      "Turn a short idea into a":"Ubah ide singkat jadi", "complete PRD":"PRD lengkap",
      "Open the studio":"Buka studio", "See features":"Lihat fitur", "See all features":"Lihat semua fitur",
      "How it works":"Cara kerja", "Three steps to a complete spec.":"Tiga langkah jadi spesifikasi lengkap.",
      "Describe":"Jelaskan", "Generate":"Buat", "Use":"Pakai",
      "Why PRD Studio":"Kenapa PRD Studio", "Capabilities":"Kemampuan",
      "Everything a spec needs, written for you.":"Semua yang dibutuhkan spesifikasi, ditulis untukmu.",
      "Get started":"Mulai", "Start free. No card, no signup.":"Mulai gratis. Tanpa kartu, tanpa daftar.",
      "Built for founders and product teams.":"Dibuat untuk founder dan tim produk.",
      // common
      "Search":"Cari", "Loading":"Memuat", "No results":"Tidak ada hasil",
      "This page does not exist.":"Halaman ini tidak ada.", "Open the studio":"Buka studio"
    }
  };

  var lang = 'en';
  try{ lang = localStorage.getItem('prd_lang') || 'en'; }catch(e){}
  window.__prdLang = lang;

  function translateText(t){
    if(lang !== 'id') return t;
    var trimmed = t.trim();
    if(!trimmed) return t;
    var map = DICT.id;
    if(map[trimmed]) return t.replace(trimmed, map[trimmed]);
    return t;
  }

  function walk(node){
    if(node.nodeType === 3){
      var nt = translateText(node.nodeValue);
      if(nt !== node.nodeValue) node.nodeValue = nt;
      return;
    }
    if(node.nodeType !== 1) return;
    var tag = node.tagName;
    if(tag === 'SCRIPT' || tag === 'STYLE' || tag === 'CODE' || tag === 'PRE') return;
    // placeholders (guarded: EN mode must stay English)
    if(lang === 'id' && node.placeholder && DICT.id[node.placeholder.trim()]) node.placeholder = DICT.id[node.placeholder.trim()];
    for(var i=0;i<node.childNodes.length;i++) walk(node.childNodes[i]);
  }

  function apply(){
    walk(document.body);
    document.documentElement.lang = (lang === 'id' ? 'id' : 'en');
  }
  if(document.body) apply(); else document.addEventListener('DOMContentLoaded', apply);

  function toggleLang(){
    lang = (lang === 'id') ? 'en' : 'id';
    try{ localStorage.setItem('prd_lang', lang); }catch(e){}
    location.reload();
  }

  function injectToggle(){
    if(document.getElementById('langBtn')) return;
    var box = (window.__prdNavTools && window.__prdNavTools()) || document.body;
    var b = document.createElement('button');
    b.id = 'langBtn'; b.className = 'theme-btn'; b.type = 'button';
    b.title = 'Language'; b.setAttribute('aria-label','Language');
    b.textContent = (lang === 'id') ? 'ID' : 'EN';
    b.addEventListener('click', toggleLang);
    box.appendChild(b);
  }
  function boot(){ injectToggle(); }
  if(document.body){ setTimeout(boot, 0); } else { document.addEventListener('DOMContentLoaded', boot); }
})();
