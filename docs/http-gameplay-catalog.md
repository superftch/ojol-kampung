# Katalog API dari halaman game KampungSebelah

Chrome menemukan **23 bundle** di halaman `/kampung` pada 15.41 WIB, 11 November 2026. Berkas diambil dari URL aset yang teramati. Analisis statis menghasilkan **269 kombinasi metode dan pola path**. [Lihat inventaris utama dan riwayat verifikasi Ojol](http-endpoints.md).

Daftar ini menunjukkan pemanggilan dari kode client. Ketersediaan server, hak akun, efek samping, idempotensi, dan skema lengkap masih perlu bukti tersendiri. Tidak ada endpoint di tabel ini yang dipanggil untuk pengujian ini.

Path dinamis memakai `{param}` saat arti segmennya belum dipastikan. Kolom query dan body menggabungkan nama field dari semua pemanggilan yang teramati pada baris itu. Field dapat muncul di varian berbeda. Tanda `?` berarti body dibentuk dari nilai yang belum ditelusuri lengkap, `…` berarti ada spread, dan `—` berarti tidak ada field yang dicatat. Kolom respons memuat field atau jenis data yang bisa ditelusuri dari konsumsi client. Tanda `—` di kolom respons berarti bentuk respons belum dicatat.

Rujukan `G` berarti `0locg-pigz8wv.js`. Angka setelah nama sumber adalah baris dan kolom 1-based, dengan kolom dihitung sebagai unit UTF-16 pada bundle asli. Tabel dapat menampilkan beberapa lokasi bila ada varian query, body, atau aksi berbeda.

## Dunia, perjalanan, dan waktu

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| GET `/api/alamat` | `q` | — | — | `G:1:57784` |
| GET `/api/bus` | — | — | — | `G:1:72325` |
| POST `/api/bus` | — | `from`, `rid`, `to` | — | `G:1:130470` |
| GET `/api/bus-keliling` | — | — | — | `G:1:124387` |
| POST `/api/bus-keliling` | — | `from`, `jalur`, `rid`, `to` | — | `G:1:124993` |
| GET `/api/kapal` | — | — | — | `G:1:72325` |
| POST `/api/kapal` | — | `from`, `rid`, `to` | — | `G:1:130470` |
| GET `/api/kereta` | — | — | — | `G:1:72325` |
| POST `/api/kereta` | — | `from`, `rid`, `to` | — | `G:1:130470` |
| GET `/api/minigame` | — | — | — | `G:1:254778` |
| GET `/api/pesawat` | — | — | — | `G:1:72325` |
| POST `/api/pesawat` | — | `from`, `rid`, `to` | — | `G:1:130470` |
| POST `/api/plots/claim` | — | `plotId`, `requestId` | — | `G:1:633284` |
| GET `/api/realtime/token` | — | — | `url` | `G:1:816049` |
| GET `/api/roads` | — | — | — | `G:1:728552` |
| POST `/api/roads/{param}/upgrade` | — | — | — | `G:1:730411` |
| GET `/api/sholat` | `kota`, `tgl` | — | — | `G:1:1002209` |
| GET `/api/sholat/kota` | `q` | — | `kota` | `G:1:997258` |
| GET `/api/situasi` | — | — | — | `G:1:100745` |
| GET `/api/streets` | `id` | — | — | `G:1:367218` |
| POST `/api/streets` | — | `days`, `name`, `requestId`, `streetId` | — | `G:1:367818` |
| GET `/api/time` | — | — | `now` | `G:1:103064`, `1dmyw8wft5-0a.js:3:36572` |
| DELETE `/api/tujuan` | — | — | — | `G:1:123368` |
| GET `/api/tujuan` | — | — | `jalan`, `pasar`, `usaha` | `G:1:57316` |
| POST `/api/tujuan` | — | `place` | — | `G:1:123472` |
| GET `/api/tujuanku` | — | — | — | `G:1:214141` |
| POST `/api/tujuanku` | — | `lepas`, `minat`, `tujuan` | — | `G:1:218080`, `G:1:219667` |
| GET `/api/world/plots` | `blocks`, `desa`, `fresh`, `part`, `v` | — | `plots` | `G:1:91814`, `G:1:92273`, `G:1:93065`, `G:1:93114` |
| GET `/api/world/plots/{plotId}` | `t` | — | — | `G:1:632376` |
| GET `/api/world/search` | `kind`, `q` | — | — | `G:1:176484` |
| GET `/api/world/sisa-kavling` | — | — | — | `1dmyw8wft5-0a.js:3:4565` |

## Ojol, kerja, dan kegiatan harian

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| GET `/api/daily` | — | — | — | `G:1:231366` |
| POST `/api/daily/bakti` | — | — | — | `G:1:247635` |
| POST `/api/daily/checkin` | — | — | — | `G:1:237137` |
| GET `/api/daily/garden` | — | — | — | `G:1:858804` |
| POST `/api/daily/garden/{param}` | — | `action`. `action` teramati `panen`, `rawat`, `tanam` | — | `G:1:242298`, `G:1:242524`, `G:1:242773`, `G:1:859900` |
| GET `/api/daily/house` | `plotId` | — | — | `G:1:250213` |
| GET `/api/daily/ronda` | — | — | — | `G:1:556454` |
| POST `/api/daily/ronda` | — | `action`, `post`. `action` teramati `claim`, `join` | — | `G:1:553586`, `G:1:555298` |
| POST `/api/daily/sapa` | — | `plotId` | — | `G:1:448143` |
| POST `/api/daily/sell` | — | `item`, `qty`, `requestId` | — | `G:1:243843` |
| POST `/api/daily/tasks/balai` | — | — | — | `G:1:232096` |
| POST `/api/daily/tasks/{param}` | — | — | — | `G:1:232255` |
| POST `/api/daily/visit` | — | `gift`, `plotId` | — | `G:1:251271` |
| POST `/api/daily/vote` | — | `plotId` | — | `G:1:251864` |
| POST `/api/job-offers/{param}/accept` | — | — | — | `G:1:315245` |
| POST `/api/job-offers/{param}/cancel` | — | — | — | `G:1:701790` |
| POST `/api/job-offers/{param}/decline` | — | — | — | `G:1:315437` |
| POST `/api/jobs/perpanjang` | — | `contractId`, `ya` | — | `G:1:313832` |
| POST `/api/jobs/quit` | — | — | — | `G:1:679697` |
| POST `/api/jobs/start` | — | `facilityId`, `profession`, `…` | — | `G:1:664785`, `G:1:689735` |
| POST `/api/jobs/vacancy/{param}` | — | `switchJob` | — | `G:1:675556` |
| GET `/api/kebutuhan` | — | — | — | `G:1:112031` |
| POST `/api/kebutuhan/bensin` | — | `petak`, `ride` | — | `G:1:118077` |
| POST `/api/kebutuhan/rawat-rumah` | — | — | — | `G:1:560473` |
| GET `/api/kerja-malam` | — | — | — | `G:1:593893` |
| POST `/api/kerja-malam` | — | `action`, `key`, `plotId`, `putaran`, `tangkap`, `titik`. `action` teramati `bersih`, `bersih-batal`, `bersih-selesai`, `lampu`, `mulai`, `patroli`, `titik` | — | `G:1:133809`, `G:1:599320`, `G:1:600562`, `G:1:600862`, `G:1:601313`, `G:1:601549`, `G:1:601715` |
| GET `/api/ojol` | — | — | `bars`, `history`, `trip` | `G:1:264932` |
| POST `/api/ojol` | — | `action`, `vehicle`. `action` teramati `ambil`, `berhenti`, `daftar`, `selesai` | `netMilli` dan `warga` untuk `selesai` | `G:1:266239`, `G:1:267662`, `G:1:268561`, `G:1:269939` |
| GET `/api/ojol/pesan` | — | — | — | `G:1:507173` |
| POST `/api/ojol/pesan` | — | `action`, `requestId`, `…`. `action` teramati `batal`, `pesan` | — | `G:1:507611`, `G:1:508025` |
| POST `/api/rest` | — | `home` | — | `G:1:650733` |
| POST `/api/rest/schedule` | — | `auto`, `from`, `to` | — | `G:1:660034` |
| POST `/api/skills` | — | `action`, `requestId`, `track`. `action` teramati `rush` | — | `G:1:691383`, `G:1:691505` |
| POST `/api/speedup` | — | `id`, `kind`, `requestId` | — | `G:1:661385` |

## Usaha, pasar, dan belanja

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| POST `/api/businesses` | — | `catalogId`, `plotId`, `requestId` | — | `G:1:644570` |
| GET `/api/businesses/forecast` | `catalogId`, `plotId` | — | — | `G:1:632675` |
| GET `/api/businesses/{param}/bahan` | — | — | — | `G:1:394224` |
| POST `/api/businesses/{param}/bahan` | — | `hari`, `requestId` | — | `G:1:396425` |
| POST `/api/businesses/{param}/buka` | — | — | — | `G:1:693354` |
| POST `/api/businesses/{param}/dagangan` | — | `items` | — | `G:1:383416` |
| POST `/api/businesses/{param}/jam` | — | `openHours` | — | `G:1:393545` |
| GET `/api/businesses/{param}/melaut` | `t` | — | — | `G:1:350960` |
| POST `/api/businesses/{param}/melaut` | — | `action`. `action` teramati `berangkat`, `jual` | — | `G:1:352213`, `G:1:352853` |
| POST `/api/businesses/{param}/nama-menu` | — | `names` | — | `G:1:385616` |
| POST `/api/businesses/{param}/name` | — | `name` | — | `G:1:380774` |
| POST `/api/businesses/{param}/offers` | — | `nickname` | — | `G:1:702662` |
| GET `/api/businesses/{param}/report` | — | — | — | `G:1:391440` |
| POST `/api/businesses/{param}/roboh` | — | — | — | `G:1:803717` |
| POST `/api/businesses/{param}/upgrade` | — | `catalogId`, `requestId` | — | `G:1:711092` |
| POST `/api/businesses/{param}/vacancy` | — | `rateMilliDay`, `slots` | — | `G:1:672009` |
| POST `/api/businesses/{param}/vacancy/close` | — | — | — | `G:1:670403` |
| POST `/api/businesses/{param}/withdraw` | — | `amountMilli`, `requestId` | — | `G:1:693624` |
| GET `/api/catalog` | — | — | — | `G:1:705036` |
| GET `/api/jualan` | — | — | — | `G:1:257054` |
| POST `/api/jualan` | — | `action`, `dagangan`, `kind`, `requestId`. `action` teramati `buka`, `dagangan`, `gerobak`, `lapak`, `upgrade` | — | `G:1:259935`, `G:1:261243`, `G:1:261665`, `G:1:262100` |
| GET `/api/makan-bersama` | — | — | — | `G:1:581943` |
| POST `/api/makan-bersama` | — | `?` | — | `G:1:583413` |
| POST `/api/makan-bersama/batal` | — | `eventId` | — | `G:1:583221` |
| POST `/api/makan-bersama/makan` | — | `eventId` | — | `G:1:583094` |
| POST `/api/makan-bersama/patungan` | — | `eventId`, `koin`, `requestId` | — | `G:1:582931` |
| GET `/api/nongkrong` | — | — | — | `G:1:68347` |
| GET `/api/nongkrong/{businessId}` | — | — | `now`, `orang` | `G:1:565907` |
| POST `/api/nongkrong/{businessId}` | — | `aksi`, `item`, `requestId` | `items`, `totalMilli` | `G:1:569748`, `G:1:570634` |
| POST `/api/promo/redeem` | — | `code` | `rewardMilli` | `G:1:782225` |
| GET `/api/shops/{businessId}` | — | — | — | `G:1:252104` |
| POST `/api/shops/{businessId}/buy` | — | `item`, `requestId` | — | `G:1:253456` |
| POST `/api/shops/{param}/cetak` | — | `color`, `produk`, `requestId`, `text` | — | `G:1:579887` |

## Rumah, tanah, dan kendaraan

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| POST `/api/constructions` | — | `catalogId`, `color`, `requestId`, `…` | — | `G:1:707465`, `G:1:709919` |
| GET `/api/houses` | — | — | — | `G:1:279594` |
| GET `/api/houses/adat` | — | — | — | `G:1:300072` |
| POST `/api/houses/adat` | — | `plotId`, `requestId`, `style` | — | `G:1:303085` |
| POST `/api/houses/adat/pasang` | — | `plotId`, `style` | — | `G:1:302464` |
| POST `/api/houses/auctions` | — | `plotId`, `requestId`, `startPriceMilli` | — | `G:1:284016` |
| POST `/api/houses/auctions/{param}/bid` | — | `amountMilli`, `requestId` | — | `G:1:289377` |
| POST `/api/houses/auctions/{param}/cancel` | — | — | — | `G:1:281229` |
| POST `/api/houses/build` | — | `plotId`, `requestId` | — | `G:1:294918` |
| POST `/api/houses/home` | — | `plotId` | — | `G:1:282736` |
| GET `/api/houses/land` | `plotId` | — | — | `G:1:290030` |
| POST `/api/houses/land` | — | `plotIds`, `requestId`, `withHouse` | — | `G:1:292588` |
| POST `/api/houses/merge` | — | `plotIds`, `requestId` | — | `G:1:285530` |
| GET `/api/houses/yard` | `plotId`, `t` | — | — | `G:1:295608` |
| POST `/api/houses/yard` | — | `action`, `listingId`, `plotId`, `priceMilli`, `requestId`. `action` teramati `buy`, `cancel`, `list` | — | `G:1:296556`, `G:1:297410`, `G:1:299219` |
| GET `/api/kendaraan` | — | — | — | `G:1:860310` |
| POST `/api/kendaraan/{param}` | — | `requestId`, `…` | — | `G:1:1070484` |
| DELETE `/api/lampu` | — | — | — | `G:1:309395` |
| GET `/api/lampu` | — | — | — | `G:1:307106` |
| POST `/api/lampu` | — | `aksi`, `areaId`, `color`, `level`, `model`, `requestId` | — | `G:1:308916`, `G:1:310801` |
| GET `/api/land` | — | — | — | `G:1:731400` |
| POST `/api/land/purchase` | — | `idempotencyKey`, `kind`, `plotIds` | — | `G:1:734310` |
| POST `/api/pekarangan` | — | — | — | `G:1:131977` |
| GET `/api/pekarangan/kopdes` | — | — | — | `G:1:408741` |
| POST `/api/pekarangan/kopdes` | — | `item`, `kopdes`, `requestId` | — | `G:1:408386` |
| GET `/api/plans` | — | — | — | `G:1:735823` |
| GET `/api/rumah/interior` | — | — | — | `G:1:867311` |
| POST `/api/rumah/interior` | — | `gaya`, `layout`, `version` | — | `G:1:857712` |
| POST `/api/rumah/interior/beli` | — | `bayar`, `item`, `requestId`, `toko` | — | `G:1:897491` |
| GET `/api/rumah/interior/lihat` | `plotId` | — | `bentuk` | `G:1:867311` |
| POST `/api/rumah/pengaturan` | — | `?` | — | `G:1:906175` |
| POST `/api/rumah/suka` | — | `plotId`, `suka` | — | `G:1:870454` |

## Profil, perbankan, dan pembayaran

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| GET `/api/bank` | — | — | — | `G:1:355858` |
| POST `/api/bank/cek` | — | `accountNo` | — | `G:1:12001` |
| POST `/api/bank/ke-dompet` | — | `amountMilli`, `requestId` | — | `G:1:13003` |
| GET `/api/bank/mobile` | — | — | — | `G:1:11519` |
| POST `/api/bank/open` | — | `projectId`, `requestId` | — | `G:1:358040` |
| POST `/api/bank/penerima` | — | `accountNo`, `hapus`, `label` | — | `G:1:12409`, `G:1:12580` |
| POST `/api/bank/setor` | — | `amountMilli`, `projectId`, `requestId` | — | `G:1:360036` |
| POST `/api/bank/tarik` | — | `amountMilli`, `projectId`, `requestId` | — | `G:1:360384` |
| POST `/api/bank/transfer` | — | `accountNo`, `amountMilli`, `requestId` | — | `G:1:12088` |
| GET `/api/bpjs` | — | — | — | `G:1:362261` |
| POST `/api/bpjs/bayar` | — | `projectId`, `requestId` | — | `G:1:362716` |
| POST `/api/fees/pay` | — | — | — | `G:1:755065` |
| GET `/api/game/me` | `biz` | — | — | `G:1:93660`, `G:1:93713` |
| GET `/api/hadiah-aktif` | — | — | — | `G:1:220332` |
| POST `/api/hadiah-aktif` | — | — | `view` | `G:1:221979` |
| GET `/api/me/avatar` | — | — | `look` | `G:1:3358` |
| POST `/api/me/avatar` | — | `avatar` | — | `G:1:8932` |
| POST `/api/me/avatar/beli` | — | `businessId`, `item`, `requestId` | — | `G:1:7962` |
| POST `/api/me/delete` | — | `confirm` | — | `G:1:758964` |
| GET `/api/me/koin` | `after` | — | — | `G:1:744161`, `G:1:744309` |
| POST `/api/me/koin-news` | — | `rewards`, `topups` | — | `G:1:187068` |
| POST `/api/me/nickname` | — | `nickname` | — | `G:1:757247` |
| POST `/api/me/social` | — | `allow` | — | `G:1:758499` |
| POST `/api/topups` | — | `points`, `requestId` | — | `G:1:750592` |
| POST `/api/topups/check` | — | — | — | `G:1:94530` |
| POST `/api/topups/{param}` | — | — | — | `G:1:97966` |
| POST `/api/topups/{param}/simulate` | — | — | — | `G:1:743646` |

## Komunikasi, relasi, dan media

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| GET `/api/ajak` | — | — | — | `G:1:426052` |
| GET `/api/audio/unggah` | — | — | `aktif` | `G:1:436096` |
| POST `/api/audio/unggah` | — | `name`, `size` | `uploadUrl`, `url` | `G:1:436505` |
| GET `/api/baliho` | `id` | — | — | `G:1:51743` |
| POST `/api/baliho` | — | `advertiser`, `contact`, `days`, `headline`, `image`, `link`, `requestId`, `spotId`, `subline`, `theme` | — | `G:1:44072` |
| POST `/api/baliho/bayar/{param}` | — | — | — | `G:1:48899` |
| POST `/api/baliho/bayar/{param}/simulasi` | — | — | — | `G:1:51292` |
| POST `/api/baliho/{param}/batal` | — | — | — | `G:1:55211` |
| POST `/api/baliho/{param}/bayar` | — | — | — | `G:1:55602` |
| GET `/api/baliho/{param}/gambar` | — | — | `gambar` | `24wi7feds2ycd.js:1:13964` |
| GET `/api/chat` | `toa` | — | — | `G:1:98881`, `G:1:791317` |
| GET `/api/chat/peer` | `plotId` | — | — | `G:1:784612` |
| GET `/api/chat/rt` | `after` | — | `messages`, `reaksi` | `G:1:484334` |
| POST `/api/chat/rt` | — | `body`, `reaksi`, `replyTo` | `at`, `reaksi` | `G:1:484589`, `G:1:484760` |
| GET `/api/chat/search` | `q` | — | — | `G:1:788733` |
| POST `/api/chat/settings` | — | `enabled` | — | `G:1:784327` |
| POST `/api/chat/threads` | — | `pejabat`, `plotId` | — | `G:1:784810`, `G:1:786431` |
| GET `/api/chat/{threadId}` | `after` | — | — | `G:1:796410`, `G:1:796662` |
| POST `/api/chat/{threadId}` | — | `body`, `reaksi`, `replyTo` | — | `G:1:795963`, `G:1:796156` |
| POST `/api/chat/{threadId}/block` | — | `block` | — | `G:1:798053` |
| POST `/api/chat/{threadId}/report` | — | `note`, `reason` | — | `G:1:798934` |
| GET `/api/koran` | `tanggal` | — | — | `G:1:224014` |
| POST `/api/koran/langganan` | — | `requestId` | — | `G:1:224678` |
| GET `/api/pasangan` | — | — | — | `G:1:1011251` |
| POST `/api/pasangan` | — | `action`, `friendId`, `rumah`. `action` teramati `ajak`, `pindah-keluar` | — | `G:1:1014758`, `G:1:1018015` |
| POST `/api/pasangan/kas` | — | `koin`, `requestId` | — | `G:1:1013592` |
| POST `/api/pasangan/{param}` | — | `action`. `action` teramati `batal`, `terima`, `tolak` | — | `G:1:1011559`, `G:1:1015986`, `G:1:1016433` |
| GET `/api/pejabat` | `facility` | — | — | `G:1:786068` |
| GET `/api/push` | — | — | `muted`, `publicKey` | `G:1:274324` |
| POST `/api/push/prefs` | — | `muted` | — | `G:1:273653` |
| POST `/api/push/subscribe` | — | `subscription` | — | `G:1:274761` |
| POST `/api/push/test` | — | — | — | `G:1:275468` |
| POST `/api/push/unsubscribe` | — | `endpoint` | — | `G:1:275239` |
| GET `/api/rooms/ping` | `after` | — | — | `G:1:991626` |
| POST `/api/rooms/report/{param}` | — | `reason` | — | `G:1:452047` |
| GET `/api/rooms/{room}` | `after` | — | `messages`, `reaksi` | `G:1:450635` |
| POST `/api/rooms/{room}` | — | `body`, `reaksi`, `replyTo` | `at`, `reaksi` | `G:1:451706`, `G:1:451877` |
| POST `/api/rooms/{room}/join` | — | — | — | `G:1:544293` |
| POST `/api/rooms/{room}/leave` | — | — | — | `G:1:545160` |
| GET `/api/selfie` | `spot` | — | — | `G:1:913475` |
| POST `/api/selfie` | — | `golden`, `ids`, `image`, `phase`, `rain`, `spot` | — | `G:1:913801` |
| GET `/api/selfie/galeri` | `before` | — | — | `G:1:918961` |
| POST `/api/selfie/hadir` | — | `spot` | — | `G:1:120473` |
| GET `/api/selfie/{param}/foto` | — | — | `gambar` | `G:1:919755` |
| POST `/api/selfie/{param}/hapus` | — | — | — | `G:1:920986` |
| GET `/api/teman` | — | — | — | `G:1:1019398` |
| POST `/api/teman` | — | `plotId` | — | `G:1:1025662` |
| GET `/api/teman/cari` | `q` | — | — | `G:1:1026052` |
| POST `/api/teman/pengaturan` | — | `friendsOnly` | — | `G:1:1024551` |
| POST `/api/teman/{param}` | — | `action`. `action` teramati `hapus`, `terima`, `tolak` | — | `G:1:1021111`, `G:1:1021371`, `G:1:1022330` |
| GET `/api/toa` | — | — | — | `G:1:30761` |
| POST `/api/toa` | — | `asKades`, `body`, `key` | — | `G:1:29073`, `G:1:31178` |
| POST `/api/toa/{param}/reply` | — | `body` | — | `G:1:27899` |
| POST `/api/toa/{param}/report` | — | `reason` | — | `G:1:31550` |

## Pemerintahan, keamanan, dan layanan desa

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| GET `/api/admin/kades-chat` | `unread` | — | — | `G:1:505802` |
| POST `/api/admin/keamanan` | — | `kind` | — | `G:1:405341` |
| POST `/api/aspirations` | — | `?` | — | `G:1:737098` |
| GET `/api/aspirations/mine` | — | — | — | `G:1:735741` |
| GET `/api/balai` | `desa` | — | — | `G:1:775814`, `G:1:775865` |
| GET `/api/facilities/{param}` | — | — | — | `G:1:765202` |
| POST `/api/facilities/{param}/nama` | — | `hari`, `nama`, `requestId` | — | `G:1:371805` |
| POST `/api/facilities/{param}/upgrade` | — | — | — | `G:1:763976` |
| POST `/api/facilities/{param}/use` | — | `requestId`, `track` | — | `G:1:767069` |
| POST `/api/keamanan/call` | — | `incidentId`, `plotId` | — | `G:1:401416` |
| POST `/api/keamanan/help` | — | `plotId` | — | `G:1:637969` |
| POST `/api/keamanan/insurance` | — | `requestId` | — | `G:1:656735` |
| POST `/api/keamanan/repair` | — | `incidentId` | — | `G:1:655667` |
| POST `/api/keamanan/seen` | — | `ids` | — | `G:1:177551` |
| GET `/api/kejadian` | — | — | — | `G:1:101479` |
| POST `/api/kejadian/bantu` | — | `plotId` | — | `G:1:313377` |
| POST `/api/kejadian/dilihat` | — | `id` | — | `G:1:164899` |
| POST `/api/kejadian/perbaiki` | — | `cara`, `plotId` | — | `G:1:164986` |
| GET `/api/pilkades` | — | — | — | `G:1:341400` |
| POST `/api/pilkades` | — | `?` | — | `G:1:341686` |
| GET `/api/pilkades/banner` | — | — | — | `G:1:338209` |
| GET `/api/program` | — | — | — | `G:1:473682` |
| POST `/api/projects/{param}/contributions` | — | `points`, `requestId` | — | `G:1:722865` |
| POST `/api/projects/{param}/speedup` | — | `maxPriceMilli`, `option`, `requestId` | — | `G:1:724741` |
| GET `/api/proposals` | `aktif` | — | — | `G:1:717360` |
| POST `/api/proposals/{param}/vote` | — | `support` | — | `G:1:726288` |
| GET `/api/rt` | — | — | — | `G:1:495851` |
| POST `/api/rt` | — | `?` | — | `G:1:496819` |
| GET `/api/rt/bangun` | — | — | — | `G:1:489151` |
| POST `/api/rt/bangun` | — | `catalogId`, `rot`, `siteId` | — | `G:1:491189` |
| GET `/api/rt/gapura` | — | — | — | `G:1:492127` |
| POST `/api/rt/gapura` | — | `?` | — | `G:1:495220` |
| GET `/api/survei` | — | — | — | `G:1:415707` |
| POST `/api/survei` | — | `nanti`, `…` | — | `G:1:416763`, `G:1:419908` |
| POST `/api/voting/{param}` | — | `choice` | — | `G:1:37533` |

## Acara, hobi, dan pendaftaran

| Metode dan path | Query | Body | Respons | Sumber |
| --- | --- | --- | --- | --- |
| GET `/api/bukit` | — | — | — | `G:1:119857` |
| POST `/api/bukit/tiket` | — | — | — | `G:1:162683` |
| GET `/api/festival` | — | — | — | `G:1:193582` |
| POST `/api/festival` | — | `action`, `akun`, `gambar`, `setujuVersi`. `action` teramati `follow_ig`, `join`, `story` | — | `G:1:197224`, `G:1:205303`, `G:1:210135` |
| GET `/api/lomba-badminton` | — | — | — | `G:1:254825` |
| GET `/api/panggung` | — | — | — | `G:1:457768` |
| DELETE `/api/panggung/daftar` | — | `eventId` | — | `G:1:438662` |
| POST `/api/panggung/daftar` | — | `bandName`, `capacity`, `description`, `kind`, `performers`, `stageId`, `startsAt`, `ticketPriceMilli`, `title`, `tracks` | — | `G:1:441807` |
| DELETE `/api/panggung/nonton` | — | `eventId` | — | `G:1:471694` |
| POST `/api/panggung/nonton` | — | `eventId` | — | `G:1:471562` |
| GET `/api/panggung/rekaman/{param}` | — | — | audio | `3rcww0vg115ek.js:1:15653`, `G:1:435136`, `G:1:441518` |
| POST `/api/panggung/tiket` | — | `eventId` | — | `G:1:462132` |
| GET `/api/peliharaan` | — | — | — | `G:1:861951` |
| POST `/api/peliharaan` | — | `baju`, `beli`, `jenis`, `porsi`, `requestId`, `…` | — | `G:1:864607`, `G:1:864932`, `G:1:865304` |
| POST `/api/peliharaan/{param}` | — | `aksi`, `baju`, `jenis`, `nama`, `requestId` | — | `G:1:115856`, `G:1:862505`, `G:1:864355`, `G:1:865076` |
| POST `/api/pos-meja/{param}` | — | `aksi`, `from`, `kartu`, `promotion`, `sisi`, `to` | — | `G:1:536613`, `G:1:537154`, `G:1:537731` |
| GET `/api/pos-ronda/{param}` | — | — | `orang` | `G:1:545686` |
| POST `/api/pos-ronda/{param}` | — | `item`, `requestId` | `jajan` | `G:1:546557` |
| GET `/api/pos-ronda/{param}/meja` | — | — | — | `G:1:535647` |
| POST `/api/pos-ronda/{param}/meja` | — | `game` | — | `G:1:539535` |
| GET `/api/tanding` | `rivals` | — | — | `G:1:922564`, `G:1:931611` |
| POST `/api/tanding` | — | `action`, `opponentId`, `?`. `action` teramati `undang` | — | `G:1:921837`, `G:1:922772` |
| POST `/api/waitlist` | — | — | — | `1dmyw8wft5-0a.js:3:2236` |

## Batas penelusuran

- Helper request utama memakai GET tanpa body dan POST bila body diberikan. Argumen metode eksplisit dapat mengganti nilai itu. Lihat `G:1:86309` dan pemanggilan terkait. Beberapa panggilan membangun path atau payload dari variabel. Katalog hanya memasukkan yang berhasil ditelusuri.

## Bundle yang diperiksa

REA CLI 6.8.0 menganalisis empat bundle yang berisi rujukan gameplay. Parser JavaScript statis memeriksa 23 bundle tanpa kegagalan parsing untuk memetakan pemanggilan. Path yang dirakit dari variabel ditelusuri lewat kode pemanggil dan helper terkait. Bundle tidak dijalankan. Manifest lokal tersimpan di `.local/http-discovery/gameplay-manifest.json` dan hasil REA di `.local/http-discovery/rea-gameplay-evidence`.

| Bundle | SHA-256 |
| --- | --- |
| `01msv9ym379u0.js` | `d5232bd1fb8d9df648d66072f9c815a1b96c04f0c7408553591be1273dd7cb31` |
| `03pm7ri0-topo.js` | `41702a8b606cf6279dfb5248b9e023ec993811c0781ee752c4ef37e6fe9725b6` |
| `0locg-pigz8wv.js` | `2bc5020de4aec988d37ccccf491aa89bcc0f7a142a4bcde45186693621054c17` |
| `0qkzqguj381eb.js` | `37de9c42f661c9a0cd7d3d003752fae3712a9f16a33e48e8dde7b1516595de05` |
| `0uyfsptumf13i.js` | `c464e8b962b03e1c1af415527143e412ad26db8c3034ab55489b73c4f8771ad9` |
| `1-z3-19vwe2f1.js` | `5220272202cdcfaba1fd7b106319f754ef6699807d21dc474b0561bba36d46b1` |
| `176y-aczcjmmi.js` | `0b1896077ade62b4235b07163d0e0db714d777c1a48ddd268453b1459da6223f` |
| `1_iezhvkqagzs.js` | `02d13e928f17ac524c619674a8ea691ee8990570592ef3aac24dffc579cab84a` |
| `1dmyw8wft5-0a.js` | `07f8610170694db073a7c185fd134cbefa31c9de928b7aac8472e6d43b60024b` |
| `1jv05aj_jkqgh.js` | `e19cf9542dd9c82bd8108091be64ce58df7790b528c36a146179b236c09f49b0` |
| `24wi7feds2ycd.js` | `19decd64e52bbde13ac4ef680131c7bc28d0132fa7b3399a37dd107e0dab3b26` |
| `2_f8-30kh8vkr.js` | `dcc445f97308ba4b506ea609eac69c938ad79e94576cab3a94f71875a1d8cf3c` |
| `2fw3usiuxlnnj.js` | `faa9d2f38dd8d2016b256b7cbaf105a57ccedca47b4045ebc2c35f9f041a113c` |
| `2g4c2hdw1i1x_.js` | `73b8b644f6821cc35fa90e7aeac577096ecc3b9bdb7b93368672d33ad815ef27` |
| `2g_6k205jx9fz.js` | `92ead3ffa1d91c45386d251a00466e889a705bc014e2f74ce33f2d731348ae73` |
| `33__ezo7fw3od.js` | `326ced86f5eed905674a09dc51a64fe0f4908a1540b26ac96e48acdfa5b2a354` |
| `38c16haq2ob3z.js` | `e04ee68fd8b8fb77e193123233cf26c611709d75c8c6bbff06ff70d08c9bc9a7` |
| `3j9op-o_52rax.js` | `a21888ca138b4c670f089ce361d583e4a82604906afa8ab7219362da5e409df4` |
| `3rcww0vg115ek.js` | `7a8d824d32d38b4844d2f2383c1afc140e93ad0d0abd14a2f7c1897948713151` |
| `41bx3p8jpx9qa.js` | `a42724de40fee0d08575a9410a38a6e9dd4dec6729c08277e6c8efb1e559a41b` |
| `43h8raf18v7c2.js` | `4e18a97231addec0d35de19a0eabf267c090130a11cedd13e976adb10c56b0ac` |
| `44b6i8chqw4y5.js` | `fbb6cee32d669bf810b9ffdb61fa672f748f903e3506d1ec8fe03748a43d8d0d` |
| `turbopack-1byz1flvc-bu1.js` | `b5f9b5199b99ab6c141f4540f0b7d0fe803c4ecf6956849ecb6e59d3d439272e` |
