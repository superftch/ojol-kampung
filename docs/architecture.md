# Arsitektur

## Alur runtime

Telegram private chat → ControlService → worker ADK BaseAgent → McpToolset stdio → Browser Harness MCP → Chromium headless.

Tidak ada model yang menghasilkan kode klik atau request game langsung. Controller deterministik membaca DOM pada tab miliknya sendiri. Instance Chrome, profil dan daemon Harness berada dalam container/volume aplikasi; tidak memakai profil desktop.

BrowserRuntime memegang file lock volume. Worker memegang lock terpisah; start ganda ditolak, termasuk ketika child baru dimulai dan belum memperoleh lock. Stop dicek selama countdown dan sebelum tindakan. Browser selalu boot ke about:blank; hanya Harness memuat satu dunia game.

Saat start/inspect/reconcile menggunakan kembali tab miliknya, agent mengirim Page.reload dengan sesi CDP eksplisit dan deadline15detik. Readiness menunggu performance.timeOrigin berubah, dokumen complete dan navigasi Kerja tersedia; dokumen lama tidak dianggap siap selama reload lambat. Timeout tidak menyebabkan reload kedua atau replay aksi game.

## Browser dan transaksi

Target ID yang dibuat sendiri disimpan dan diverifikasi sebelum reuse. Evaluasi DOM dan focus emulation memakai sesi CDP persisten yang terikat pada target itu, melalui tool MCP resmi `browser_cdp`. Timeout berlapis: response daemon15detik, request MCP25detik, batas luar panggilan30detik. MCP stdio memakai timeout request yang lebih panjang dari batas daemon beserta koneksi IPC. Error langsung dari ADK (`error` tanpa content) dibaca sebagai error tool, bukan diparse sebagai JSON kosong. Respons cacat dilaporkan dengan tipe content dan nama tool tanpa body payload. Kegagalan reset focus saat cleanup tidak menggantikan exception aksi yang sedang gagal; setelah timeout, cleanup tidak mengirim perintah baru ke transport/renderer yang baru gagal. Tanpa exception sebelumnya, kegagalan cleanup tetap dilaporkan. Origin/path game diperiksa di setiap ekspresi. Tidak mengaktifkan tab desktop atau memakai input OS.

Sebelum klik berakibat, SQLite meng-commit aksi pending beserta state awal. Setelah klik, controller memverifikasi resource/dompet atau receipt/countdown. Timeout menjadi uncertain; tidak ada retry klik. Rekonsiliasi tidak mengubah game. Receipt spesifik bisa mengonfirmasi klaim lama berdasarkan rute, waktu dan payout; source_key unik menjaga pencatatan idempoten.

Pesan tidur mengalahkan tombol Cari order yang masih terlihat. Snapshot verifikasi terakhir dipertahankan meskipun predicate belum terpenuhi. Pencarian yang sudah dimulai dapat masuk status searching, kemudian ditunggu dengan batas30detik. Rekonsiliasi menutup lifecycle pencarian setelah dua observasi konsisten dari dokumen yang sudah di-refresh: saldo/payout/history tetap sama pada hari WIB yang sama dan resource tidak bertambah. UI tanpa order menjadi closed_idle. Tawaran, perjalanan berjalan atau perjalanan selesai dengan rute dan tombol yang cocok menjadi handed_off; countdown boleh menurun pada rute yang sama. Tidak mengklaim ongkos dalam rekonsiliasi. Worker yang dimulai kemudian mengikuti state saat ini dan mencatat aksi klaim baru sebelum klik, bukan mengulang pencarian lama. Sebab perubahan resource maupun hasil klik historis tidak disimpulkan; before/after dipertahankan, selisih resource dan original_outcome=uncertain dicatat atomik dengan status. Tidak menambah cashflow. Klaim/pembelian tetap memerlukan bukti sebelumnya. State yang tidak stabil atau perubahan finansial tetap diblokir dan ditampilkan dalam diagnostik.

Produk disaring ke kebutuhan motor/data yang didukung. Planner memilih biaya per poin aman, menunda refill yang belum muat, dan mengecek ulang produk/harga/dompet tepat sebelum Beli. Poin tidak boleh melebihi100%; saldo utama dijaga≥20 dengan margin tampilan0,01. Bank tidak dianggap cash.

## Data dan laporan

`history.sqlite3` memuat runs, actions, events dan cashflows. Uang memakai Decimal/TEXT. Mode WAL dan indeks waktu mendukung laporan ketika worker menulis. Laporan default hari ini Asia/Jakarta, dengan batas UTC yang sama untuk ringkasan, per sesi dan transaksi.

Penerimaan memakai payout dari riwayat game; selisih cash dari aktivitas akun lain diabaikan. Potongan aplikasi yang sudah tercakup payout tidak dikurangi lagi. Event dan cashflow tidak dihapus oleh retensi log.

## Auth dan control plane

Telegram memvalidasi chat private, Chat ID dan sender ID. Callback tanggal diakui lalu diproses lewat grammar terbatas. Link import berupa tiket opaque sekali pakai; database hanya menyimpan hash. Viewer session HttpOnly15menit memiliki token CSRF HMAC khusus. Import dibatasi ukuran, hanya menerima cookie sesi game, diverifikasi melalui MCP dan mencabut sesi form setelah sukses.

Cookie Google, password, bearer provider dan secret Telegram tidak diteruskan ke subprocess MCP. Token bot dikecualikan dari serialisasi Settings. Nilai cookie dibawa lewat body HTTPS atau pipe stdin lokal, tidak masuk argv/ledger/log.

Production membutuhkan HTTPS, Telegram lengkap, browser terkelola dan saldo minimum20. Domain production dari konfigurasi mengalahkan override Quick Tunnel lokal yang mungkin tertinggal di volume. Compose hanya menerbitkan gateway loopback6080; TLS berada di Cloudflare. Satu container juga memuat cloudflared yang dipin digest; connector mengarah ke HTTP localhost6080. Secret token dimuat lewat file privat, tidak masuk argv/image/Git. Metrics/readiness hanya loopback2000.

## Lifecycle dan operasi

Control service memiliki child cloudflared dan memantaunya bersama browser/worker. Connector exit menghasilkan stage `tunnel.process_exit` dan menghentikan worker, sementara bot tetap bisa melaporkan error. Import Cookie/Jalankan Ojol dapat memulai connector kembali. Restart container menghentikan seluruh proses; shutdown membersihkan child tunnel sekalipun worker gagal berhenti.

Error worker/browser/control/tunnel menulis STOP dan antrean error dengan stage/action/run. Hasil timeout tidak diputar ulang. Notifikasi rutin bisa ON/OFF dan persist setelah restart; mandatory error tetap aktif. Outage Telegram menghasilkan satu notice per outage, bukan ribuan error sama. Pengiriman pending dipertahankan sampai jaringan pulih; retry dapat menggandakan notifikasi, bukan transaksi.

Log stdout dikelola rotasi Docker. Salinan delivery `.sent`/`.muted` kedaluwarsa7hari; file pending tidak dipangkas. Shutdown menunggu worker sebelum menutup browser. Restart service tidak menjalankan gameplay otomatis. Volume/browser lease juga mencegah dua controller berbagi profil aktif.

CI hanya mem-build test stage: lint, format dan tests lewat `.env.testing` dummy di image. Secret runtime, browser profile dan database pengguna dikeluarkan dari build context dan Git.
