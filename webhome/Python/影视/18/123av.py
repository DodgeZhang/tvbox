# -*- coding: utf-8 -*-
"""
123AV (123av.com) — TVBox / WebHTV 四壳通用 Python 源
=====================================================
站点架构 : SSR (Alpine.js),列表 / 详情 / 维度页数据全在 HTML 里
通道     : 标准库直连(Chrome UA),零第三方依赖 —— 壳环境可直接跑

分类体系
  一级 : 最新 / 热门 / 最近 / 今日榜 / 本周榜 / 本月榜 / 有码 / 无码 / 无码破解
         类型(477) / 女优 / 片商 / 系列
  筛选 : Type(有码·无码·破解) / Year(2000-2026) / Actress(单·多) / Sort(9 种)
  分页 : ?page=N —— 真分页,站点上限 5000 页

播放
  详情页 Alpine 内嵌  player(JSON.parse('[{"url":"https://javplayer.cc/e/<HASH>?"}]'), ...)
  GET https://javplayer.cc/stream?id=<HASH>
      → {"media":{"stream":"<m3u8>","vtt":"<字幕>"}}
  实测 8/8 命中,播放位直出 m3u8(parse=0);取不到时回退嵌入页交给壳内解析

  关键:m3u8 与**每一个分片**都要求 Referer: https://javplayer.cc/(实测不带 → 403)。
  部分壳(EXO / IJK 直连)不会把源返回的 header 带到播放请求上,症状是「列表正常、
  点开一直缓冲、分辨率和时长都是空」。故播放位默认走**本机转发**(RELAY_ON):
  源在盒子本机起一个只读转发服务,自己补齐 Referer 再吐给壳,与壳是否支持 header 无关;
  目标地址用 base64url 包裹,顺带避开 URL 里的 + 被中间层误解码。
  播放列表里另有「·直链」备用线路(直链 + 老格式 header),供认得 header 的壳使用。

说明
  ① 列表首页不带 page 参数(站点对 page=1 的边界处理与首页不完全一致)
  ② 站点 total 数字在带 page 时依然真实(逐页核对过),但页数上限固定 5000
  ③ 全部异常内部消化,坏输入返回空结构,不外抛
"""
import sys
import re
import json
import time
import random
import base64
import threading
import socketserver
import http.server
import urllib.parse
import urllib.request
import urllib.error

sys.path.append('..')
try:
    from base.spider import Spider as _Base
except Exception:
    _Base = object

HOST = "https://123av.com"
PLAYER_HOST = "https://javplayer.cc"
PLAYER_REF = "https://javplayer.cc/"    # m3u8 / 分片防盗链要求此 Referer(实测不带 → 403)
LANG = "/en"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PER_PAGE = 12          # 列表页每页卡片数(实测)
MAX_PAGE_FALLBACK = 5000

# 一级固定分类:(type_id, 名称, 路径)
FIXED = [
    ("new", "最新", "/en/new"),
    ("hot", "热门", "/en/hot"),
    ("recent", "最近", "/en/recent"),
    ("today", "今日榜", "/en/all?sort=today"),
    ("week", "本周榜", "/en/all?sort=week"),
    ("month", "本月榜", "/en/all?sort=month"),
    ("censored", "有码", "/en/censored"),
    ("uncensored", "无码", "/en/uncensored"),
    ("leaked", "无码破解", "/en/uncensored-leaked"),
]

# 维度入口:(type_id, 名称, 路径, 内容形态)
#   list  = 作品卡片(可直接播)
#   star  = 演员条目 / maker 条目 / series 条目(点开是合集)
DIMS = [
    ("actress", "女优", "/en/actresses", "star"),
    ("maker", "片商", "/en/makers", "star"),
    ("series", "系列", "/en/series", "star"),
]

TYPES = [("", "全部"), ("censored", "有码"), ("uncensored", "无码"),
         ("uncensored-leaked", "无码破解")]
ACTRESS_F = [("", "全部"), ("single", "单人"), ("multi", "多人")]
SORTS = [("release_date", "发布日期"), ("recent", "最近添加"), ("hot", "热门"),
         ("today", "今日"), ("week", "本周"), ("month", "本月"),
         ("views", "最多观看"), ("follows", "最多关注"), ("longest", "最长")]
YEARS = [""] + [str(y) for y in range(2026, 1999, -1)]

# 类型表:现网实测 477 条(slug, 展示名),数量见注释表
GENRES = [
    ("solowork", "Solowork"),  # 177,062
    ("creampie", "Creampie"),  # 164,486
    ("big-tits", "Big Boobs"),  # 124,276
    ("married-womanhousewife", "Married Woman/Housewife"),  # 91,547
    ("amateur", "Amateur"),  # 88,917
    ("high-vision", "High Vision"),  # 59,782
    ("e22f5b4c15", "Blowjob"),  # 50,928
    ("beautiful-girl", "Beautiful Girl"),  # 48,345
    ("beautiful-breasts", "Beautiful Breasts"),  # 41,839
    ("slender", "Slender"),  # 41,299
    ("gonzo", "Hameha"),  # 37,355
    ("slut", "Slut"),  # 37,226
    ("threesome-foursome", "3P/4P"),  # 34,365
    ("squirting", "Squirting"),  # 31,716
    ("digimo", "Digital"),  # 31,669
    ("cuckold-cuckolded-ntr", "Cuckold, Cuckolded, Ntr"),  # 30,438
    ("exclusive", "Exclusive"),  # 27,340
    ("over-4-hours", "4 Hours Or More"),  # 26,450
    ("paizuri", "Titjob"),  # 25,582
    ("cowgirl", "Cowgirl"),  # 24,511
    ("competitive-swimmingschool-swimwear", "Competitive Swimming/School Swimsuits"),  # 23,342
    ("lewdhard", "Lewd/Hardcore"),  # 22,718
    ("facial", "Facial"),  # 22,056
    ("shaved-pussy", "Paipan"),  # 20,529
    ("drama", "Drama"),  # 20,460
    ("schoolgirl", "Schoolgirl"),  # 20,189
    ("older-sister", "Older Sister"),  # 18,709
    ("handjob", "Handjob"),  # 18,637
    ("big-ass", "Big Ass"),  # 18,291
    ("planning", "Planning"),  # 17,300
    ("masturbation", "Masturbation"),  # 16,449
    ("adultery", "Affair"),  # 15,365
    ("nampa", "Pick-Up"),  # 15,230
    ("cunnilingus", "Cunnilingus"),  # 15,073
    ("mousozoku", "Delusion Group"),  # 14,998
    ("documentary", "Documentary"),  # 14,901
    ("incest", "Incest"),  # 14,736
    ("7889ef8307", "Cosplay"),  # 14,477
    ("bareback", "Bareback"),  # 13,769
    ("humiliation", "Humiliation"),  # 13,684
    ("sex-toys", "Toys"),  # 13,576
    ("beautiful-buttocks", "Beautiful Buttocks"),  # 13,241
    ("female-college-student", "College Girls"),  # 13,184
    ("deep-throat", "Iramachio"),  # 13,001
    ("ol", "Ol"),  # 12,552
    ("gal", "Gal"),  # 11,993
    ("uniform", "Uniform"),  # 11,920
    ("orgy", "Orgy"),  # 11,695
    ("voyeurismpeeping", "Voyeurism"),  # 11,431
    ("shame", "Shame"),  # 11,243
    ("other-fetishes", "Other Fetishes"),  # 11,085
    ("kisskiss", "Kiss"),  # 10,767
    ("anal", "Anal"),  # 10,716
    ("debut-work", "Debut Work"),  # 10,514
    ("butt-fetish", "Ass Fetish"),  # 10,261
    ("idolcelebrity", "Idols And Celebrities"),  # 10,198
    ("beautiful-legs", "Beautiful Legs"),  # 9,652
    ("dirty-talk", "Dirty Talk"),  # 9,297
    ("restraint", "Restraint"),  # 9,104
    ("bestcompilation", "Best/Compilation"),  # 8,868
    ("small-breaststiny-breasts", "Small Breasts"),  # 8,581
    ("acme-orgasm", "Acme Orgasm"),  # 8,430
    ("lotion", "Lotion/Oil"),  # 8,410
    ("gulp", "Swallow"),  # 8,406
    ("bukkake", "Bukkake"),  # 8,161
    ("mother", "Mother"),  # 7,880
    ("club-hostess-sex-worker", "Hostess, Prostitute"),  # 7,627
    ("electric-machine", "Electric Massager"),  # 7,571
    ("massage-reflex", "Massage And Refreshment"),  # 7,536
    ("subjectivity", "Subjective"),  # 7,337
    ("vibrator", "Vibe"),  # 7,283
    ("minimal-mosaic", "Girimoza"),  # 7,027
    ("pornstar", "Pornstar"),  # 6,926
    ("finger-fuck", "Fingering"),  # 6,803
    ("back", "Back"),  # 6,697
    ("pantyhosetights", "Pantyhose And Tights"),  # 6,561
    ("f0f0e4571c", "Lesbian"),  # 6,543
    ("sm", "Sm"),  # 6,382
    ("older-sisteryounger-sister", "Older Sister"),  # 6,282
    ("14bfa6bb14", "Six Nine"),  # 6,149
    ("bondage", "Bondage"),  # 6,095
    ("school-uniform", "School Uniform"),  # 6,095
    ("various-occupations", "Various Occupations"),  # 5,995
    ("chubby", "Pochari"),  # 5,874
    ("female-teacher", "Female Teacher"),  # 5,842
    ("urinationwetting", "Peeing/Peeing"),  # 5,772
    ("big-dickhuge-dick", "Big Cock"),  # 5,731
    ("outdoorexposed", "Outdoors/Exposure"),  # 5,692
    ("young-wifeyoung-wife", "Young Wife"),  # 5,486
    ("beauty-salon", "Esthetics"),  # 5,383
    ("swimsuit", "Swimwear"),  # 5,353
    ("virginity", "Virgin"),  # 5,231
    ("tall", "Tall"),  # 5,189
    ("mouth-cumshot", "Mouth Cumshot"),  # 4,734
    ("fair-skin", "Fair Skin"),  # 4,612
    ("big-breast-fetish", "Big Tits Fetish"),  # 4,570
    ("vr-only", "Vr Only"),  # 4,519
    ("m-man", "M-Man"),  # 4,487
    ("lolichildlike-look", "L**/Childlike Look"),  # 4,444
    ("sweaty", "Sweaty"),  # 4,366
    ("hot-spring", "Hot Springs"),  # 4,328
    ("beautybeautiful-woman", "Beauty/Beautiful Woman"),  # 4,300
    ("nursenurse", "Nurse"),  # 3,984
    ("cute-1", "Cute"),  # 3,949
    ("image-video", "Image Video"),  # 3,909
    ("age-bracket-30s40setc", "Age Bracket (30s/40s/etc.)"),  # 3,816
    ("devil", "Cruel"),  # 3,811
    ("lingerie", "Lingerie"),  # 3,711
    ("panty-shots", "Panchira"),  # 3,687
    ("vr", "Vr"),  # 3,663
    ("foot-fetish", "Leg Fetish"),  # 3,551
    ("petite", "Petite"),  # 3,544
    ("m-woman", "M Woman"),  # 3,541
    ("kimono", "Japanese Clothes/Yukata"),  # 3,488
    ("neat", "Neat"),  # 3,480
    ("mini-series", "Mini"),  # 3,337
    ("drag", "Drag"),  # 3,246
    ("emmanuelle", "Emmanuel"),  # 3,240
    ("mother-in-law", "Mother In Law"),  # 3,080
    ("super-milk", "Huge Breasts"),  # 3,042
    ("face-sitting", "Facesitting"),  # 2,910
    ("glasses", "Glasses"),  # 2,876
    ("harem", "Harem"),  # 2,837
    ("lesbian-kissing", "Lesbian Kiss"),  # 2,749
    ("8kvr", "8Kvr"),  # 2,744
    ("sailor-suit", "Sailor Suit"),  # 2,662
    ("virgin-1", "Virgin"),  # 2,651
    ("maid", "Maid"),  # 2,616
    ("couple", "Couple"),  # 2,499
    ("footjob", "Footjob"),  # 2,408
    ("high-quality-vr", "High Quality Vr"),  # 2,407
    ("close-up", "Close-Up"),  # 2,359
    ("shemale", "New Half"),  # 2,295
    ("mischief", "Prank"),  # 2,215
    ("immediate-saddle", "Instant"),  # 2,176
    ("confinement", "Confinement"),  # 2,157
    ("gym-clothes-bloomers", "Gym Clothes/Bloomers"),  # 2,059
    ("cross-dressingmale-girl", "Cross-Dressing/Boys"),  # 2,052
    ("bitch", "Bitch"),  # 2,013
    ("black-hair", "Black Hair"),  # 1,898
    ("actress-best-compilation", "Actress Best Compilation"),  # 1,876
    ("bath", "Bath"),  # 1,812
    ("multiple-episodes", "Multiple Stories"),  # 1,797
    ("erotic-wear", "Erotic Clothes"),  # 1,736
    ("female-boss", "Female Boss"),  # 1,657
    ("impregnate", "Pregnancy"),  # 1,632
    ("health-soap", "Health Soap"),  # 1,590
    ("post", "Posts"),  # 1,588
    ("drinking-party", "Drinking Party/Dating"),  # 1,583
    ("black-actor", "Black Actor"),  # 1,489
    ("miniskirt", "Miniskirt"),  # 1,466
    ("enema", "Enema"),  # 1,395
    ("love-affair", "Love"),  # 1,376
    ("dvd-toaster", "Dvd Toaster"),  # 1,360
    ("female-investigator", "Female Investigator"),  # 1,293
    ("original-collaboration", "Original Collaboration"),  # 1,286
    ("model", "Model"),  # 1,260
    ("dating", "Date"),  # 1,251
    ("lesbian", "Lesbian"),  # 1,228
    ("tutor", "Private Tutor"),  # 1,219
    ("school-stuff", "School Stuff"),  # 1,204
    ("sports", "Sports"),  # 1,150
    ("fan-appreciation-home-visit", "Fan Appreciation/Visit"),  # 1,128
    ("stewardess", "Stewardess"),  # 1,122
    ("torture", "T**"),  # 1,114
    ("others", "Other"),  # 1,114
    ("sunburn", "Sunburn"),  # 1,111
    ("white-actress", "White Actress"),  # 997
    ("shota", "S**"),  # 995
    ("sexy", "Sexy"),  # 954
    ("widow", "Widow"),  # 952
    ("ladydaughter", "Lady"),  # 928
    ("baby-facechildlike-face", "Baby Face/Childlike Face"),  # 927
    ("hotel", "Hotel"),  # 889
    ("rotor", "Rotor"),  # 875
    ("delusion", "Delusion"),  # 873
    ("childhood-friend", "Young Najimi"),  # 865
    ("leotards", "Leotard"),  # 848
    ("female-announcer", "Female Ana"),  # 848
    ("secretary", "Secretary"),  # 835
    ("for-women", "For Women"),  # 824
    ("manguripiledriver-position", "Manguri/Piledriver Position"),  # 823
    ("business-attire", "Business Suits"),  # 817
    ("special-effects", "Special Effects"),  # 802
    ("bunny-girl", "Bunny Girl"),  # 802
    ("reverse-number", "Reverse Nan"),  # 787
    ("hairypubic-hair", "Hairy/Pubic Hair"),  # 782
    ("breast-milk", "Breast Milk"),  # 774
    ("innocent", "Innocent"),  # 762
    ("drinking-urine", "Urine Drinking"),  # 757
    ("female-doctor", "Female Doctor"),  # 756
    ("dildo", "Dildo"),  # 751
    ("man-squirting", "Male Squirting"),  # 715
    ("subordinatescolleagues", "Subordinates/Colleagues"),  # 707
    ("instructor", "Instructor"),  # 695
    ("short-hair", "Short Hair"),  # 666
    ("muscle", "Muscle"),  # 664
    ("waist", "Waist"),  # 619
    ("portio", "Porchio"),  # 605
    ("nice-bodygreat-style", "Nice Body/Great Style"),  # 604
    ("foreign-object-insertion", "Foreign Object Insertion"),  # 594
    ("no-bra", "Nobra"),  # 585
    ("car-sex", "Car Sex"),  # 581
    ("travel", "Travel"),  # 572
    ("sex-position-misc", "Sex Position (misc)"),  # 566
    ("actionfighting", "Action/Fighting"),  # 560
    ("western-pinsoverseas-imports", "Western Pins &amp; Imports"),  # 545
    ("race-queen", "Race Queen"),  # 544
    ("cusco", "Kusuko"),  # 535
    ("athlete", "Athlete"),  # 527
    ("white-of-the-eyesfainting", "White Of The Eyes/Fainting"),  # 520
    ("hospitalclinic", "Hospitals And Clinics"),  # 495
    ("proprietress-landlady", "Landlady/Mistress"),  # 494
    ("tsundere", "Tsundere"),  # 490
    ("onasapo", "Ona Support"),  # 490
    ("spanking", "Spanking"),  # 472
    ("naked-apron", "Nude Apron"),  # 468
    ("rape", "R**"),  # 467
    ("fantasy", "Fantasy"),  # 456
    ("long-hair", "Long Hair"),  # 455
    ("beautiful-skinwhitening", "Beautiful Skin/Whitening"),  # 444
    ("daughteradoptive-daughter", "Daughter/Adopted Daughter"),  # 429
    ("molesterchikan", "Molester/Chikan"),  # 421
    ("ff46e22870", "Glory Quest 40% Off Sale"),  # 418
    ("vip", "Vip"),  # 417
    ("7520ed52ed", "Beautiful butt"),  # 413
    ("knee-socks", "Knee Socks"),  # 411
    ("aunt", "Aunt"),  # 407
    ("dance", "Dance"),  # 367
    ("queen", "Mistress"),  # 361
    ("club-activities-manager", "Club/Manager"),  # 360
    ("cat-earsbeast-type", "Cat Ears/Animals"),  # 358
    ("bodycon", "Bodycon"),  # 358
    ("bride", "Bride"),  # 350
    ("teenyoung-18", "Teen/Young (18+)"),  # 349
    ("female-warrior", "Female Warrior"),  # 349
    ("fist", "Fist"),  # 346
    ("premature-ejaculation", "Premature Ejaculation"),  # 339
    ("pregnant-woman", "Pregnant Women"),  # 338
    ("pervert", "Pervert"),  # 323
    ("sod3040", "SOD30周年40%オフセール"),  # 308
    ("brutal-expression", "Cruelty"),  # 298
    ("time-stop", "Time Stop"),  # 294
    ("grandfather", "Grandpa"),  # 292
    ("58fc0c7a98", "raw sex"),  # 292
    ("transformation-heroine", "Transformation Heroine"),  # 291
    ("action", "Action"),  # 289
    ("how-to", "How To"),  # 288
    ("soft-body", "Soft Body"),  # 284
    ("high-sensitivity", "High Sensitivity"),  # 281
    ("asian-actresses", "Asian Actresses"),  # 280
    ("scatology", "Scat"),  # 260
    ("puke", "Vomit"),  # 257
    ("blonde", "Blonde"),  # 252
    ("sokkurisan", "Sokkurisan"),  # 252
    ("interview", "Interview"),  # 249
    ("nipple-slip", "Breast Flashing"),  # 245
    ("nipple-play", "Nipple Play"),  # 244
    ("celebrity", "Celebrity"),  # 241
    ("no-panties", "No Pants"),  # 236
    ("breeding", "Breeding"),  # 236
    ("swapping", "Swapping"),  # 234
    ("drunk", "Drunk"),  # 233
    ("sex-changefeminization", "Gender-Bending/Feminization"),  # 232
    ("m", "M"),  # 227
    ("tickling", "Kusuguri"),  # 222
    ("dark-skin", "Dark Skin"),  # 222
    ("defecation", "Defecation"),  # 216
    ("av-3", "AV女優"),  # 215
    ("eb19a4e304", "Cute"),  # 211
    ("campaign-girl", "Candy"),  # 210
    ("dc863e2c60", "beauty"),  # 210
    ("waitress", "Waitress"),  # 201
    ("nose-hook", "Nose Hook"),  # 192
    ("dark-system", "Dark"),  # 191
    ("sumata-non-penetrative", "Sumata (Non-penetrative)"),  # 187
    ("nationality-taiwanrussiahalf", "Nationality (Taiwan/Russia/Half)"),  # 185
    ("limited-time-sale", "Limited Time Sale"),  # 182
    ("loose-socks", "Loose Socks"),  # 181
    ("d10e314b86", "巨乳キャンペーン"),  # 176
    ("abuse", "Insults"),  # 175
    ("mask-mask", "Masks"),  # 170
    ("mom-friend", "Mom Friends"),  # 169
    ("beautiful-pussy", "Beautiful Pussy"),  # 158
    ("anal-sex", "Anal Sex"),  # 150
    ("cheongsam-dress", "Chinese Dress"),  # 149
    ("anime-characters", "Anime Characters"),  # 145
    ("breasts-generic-ungraded", "Breasts (generic, ungraded)"),  # 145
    ("futanari", "Futanari"),  # 144
    ("otaku", "Otaku"),  # 141
    ("limited-to-fanza-distribution", "Fanza Exclusive"),  # 136
    ("foreigner", "Foreigner"),  # 132
    ("1e15769cb4", "Delusional Tribe - Emmanuel 40% Off Sale"),  # 128
    ("receptionist", "Receptionist"),  # 124
    ("a632acd889", "Beautiful woman"),  # 123
    ("brown-hair", "Brown Hair"),  # 122
    ("4aed778d5c", "Next Group Thanksgiving Sale 40% Off"),  # 121
    ("b660a1357d", "Oral ejaculation"),  # 120
    ("cheerleader", "Cheer Girls"),  # 118
    ("doll", "Doll"),  # 118
    ("82688fd853", "20 years old"),  # 115
    ("de76af0a33", "2 ejaculations"),  # 114
    ("b0e982044a", "アナルセックス(男ノ娘)"),  # 114
    ("tentacles", "Tentacles"),  # 113
    ("yoga", "Yoga"),  # 112
    ("candle", "Candles"),  # 112
    ("companion", "Companion"),  # 105
    ("gag-comedy", "Gag Comedy"),  # 104
    ("cny", "Former Idol"),  # 101
    ("73ea7f13a9", "1-day shoot"),  # 96
    ("grandma", "Grandma"),  # 95
    ("hairstyle-twintailponytailbob", "Hairstyle (Twintail/Ponytail/Bob)"),  # 91
    ("bus-tour-guide", "Bus Guide"),  # 89
    ("sci-fi", "Science Fiction"),  # 86
    ("shrine-maiden", "Shrine Maiden"),  # 86
    ("martial-artist", "Fighter"),  # 84
    ("s", "S woman"),  # 84
    ("3d", "3D"),  # 83
    ("blindfold", "Blindfold"),  # 78
    ("g-1", "G cup"),  # 76
    ("indies", "Indies"),  # 74
    ("beauty", "Beauty"),  # 73
    ("hypnosisbrainwashing", "Hypnosis/Brainwashing"),  # 71
    ("over-16-hours", "16+ Hours"),  # 70
    ("w", "W-finger man"),  # 70
    ("set-product", "Set Products"),  # 67
    ("06bec123a2", "Boobs"),  # 66
    ("magical-girl", "Magical Girl"),  # 64
    ("kunoichi", "Kunoichi"),  # 63
    ("reprint", "Reprint"),  # 62
    ("a815466d96", "Handjob"),  # 62
    ("4k", "4K shooting"),  # 62
    ("417110abc4", "Cute"),  # 61
    ("av-open-2014-heavyweight", "Av Open 2014 Heavyweight"),  # 57
    ("seasonalholiday", "Seasonal/Holiday"),  # 57
    ("ae186fcf7f", "Lolita type"),  # 51
    ("confession-of-experience", "Experience Confession"),  # 49
    ("neglect", "Abandoned"),  # 47
    ("b1b332b734", "Ejaculation twice"),  # 45
    ("f-1", "F-cup"),  # 44
    ("medium-hair", "Medium Hair"),  # 44
    ("tattoo", "Tattoo"),  # 43
    ("av-open-2014-middle-class", "Av Open 2014 Middle Class"),  # 43
    ("b30c1a985e", "raw"),  # 42
    ("9e108af5d0", "None"),  # 41
    ("av-open-2015-planning-division", "Av Open 2015 Planning Division"),  # 39
    ("coprophagy", "Coprophagy"),  # 38
    ("511ff31f89", "Congratulations on becoming a new adult! 40% off sale for you, the adult!"),  # 38
    ("firststar40", "Mercury, Firststar, 40% off sale"),  # 38
    ("boyish", "Dryish"),  # 37
    ("dialect", "Dialect"),  # 36
    ("2ee8e88780", "One-take shot"),  # 36
    ("2116ccf696-1", "Idol"),  # 35
    ("9198b827fe", "Seedke"),  # 35
    ("3144284b4b", "missionary position"),  # 34
    ("firststar40-1", "マーキュリー・FirstStar・ワー40%オフセール"),  # 34
    ("33a0e9d009-1", "Coarse hair"),  # 33
    ("ca", "Ca"),  # 33
    ("30", "30s"),  # 33
    ("ab6c23aea2", "past 1"),  # 33
    ("edging", "Ebli"),  # 33
    ("c08a240662-1", "ディスクオンデマンドセール"),  # 33
    ("2de202ecda", "Prestige Winter Festival - Up to 50% Off"),  # 33
    ("v-cinema", "V-Cinema"),  # 32
    ("horror", "Horror"),  # 32
    ("40-4", "妄想族・エマニエル40%オフセール"),  # 32
    ("d97496ec3b", "fellatio"),  # 31
    ("40-2", "プレステージ40%オフセール"),  # 31
    ("v", "VTuber"),  # 31
    ("e-1", "E-cup"),  # 30
    ("curly-hair", "Curly Hair"),  # 30
    ("70d2b9a4d3", "Small breasts"),  # 30
    ("89a5a51891", "Global Media 40% Off Sale"),  # 29
    ("716b636399", "Bonus included"),  # 29
    ("collaboration-work", "Collaboration Works"),  # 29
    ("3c4e72db34", "iPoke Campaign"),  # 28
    ("fc43e2da49", "Beautiful skin"),  # 27
    ("1ff879de5d", "sensitive"),  # 26
    ("f5627f945b", "Ika-se game"),  # 25
    ("h-1", "H-cup"),  # 24
    ("6f4922f455", "18"),  # 24
    ("4aa5600cd7", "small breasts"),  # 23
    ("420073d82a", "Round 2"),  # 23
    ("av-open-2015-maniafetish-section", "Av Open 2015 Mania/Fetish Section"),  # 23
    ("c08a240662", "Disc-on-Demand Sale"),  # 23
    ("high-heels-1", "High Heels"),  # 23
    ("8bc0a4b00d", "3 ejaculations"),  # 23
    ("paradise-tv", "Paradise Tv"),  # 23
    ("b48b612c43", "pregnancy"),  # 22
    ("av-open-2016-dramadocumentary-category", "Av Open 2016 Drama/Documentary Category"),  # 22
    ("threesome-foursome-1", "Threesome / Foursome"),  # 21
    ("gay", "Gay"),  # 21
    ("av-open-2016-maniafetish-section", "Av Open 2016 Mania/Fetish Section"),  # 21
    ("59b6cd8984", "Prestige 40% Off Sale"),  # 20
    ("4ac27f00cf", "Tall"),  # 20
    ("de0737b86a", "pubic hair"),  # 20
    ("06ae3252c9", "Half outside, half inside"),  # 20
    ("3dbdbd029d", "Manguri-gaeshi"),  # 20
    ("bondage-1", "Bondage"),  # 20
    ("6f61b9f992", "Innocent (Naive) type"),  # 20
    ("18", "18 years old"),  # 19
    ("9eb330fb55", "2 shots"),  # 19
    ("av-open-2015-smhard", "Av Open 2015 Sm/Hard"),  # 19
    ("mgs", "MGS Exclusive Bonus Footage"),  # 18
    ("miniskirt-police", "Miniscapolis"),  # 18
    ("gothic-lolita", "Gothic Lolita"),  # 18
    ("e538d644dd", "2 consecutive ejaculations"),  # 17
    ("72c9b14385", "Raw cumshot"),  # 17
    ("avopen2016", "Avopen2016 Planning Department"),  # 17
    ("av-open-2018-maniafetish-section", "Av Open 2018 Mania/Fetish Section"),  # 17
    ("285f1d32d0", "Pubic hair"),  # 16
    ("av-open-2016-amateur-division", "Av Open 2016 Amateur Division"),  # 16
    ("av-open-2015-maiden-division", "Av Open 2015 Maiden Division"),  # 15
    ("av-open-2016-planning-division", "Av Open 2016 Planning Division"),  # 15
    ("70ecf2ba69", "Baby face"),  # 15
    ("40", "ネクストグループ感謝祭40%オフセール"),  # 15
    ("027267b1e5", "Pervert"),  # 15
    ("29b54e86a8", "Around 40"),  # 15
    ("57f900cfa6", "Namahame"),  # 14
    ("1ac199e19d", "No staging"),  # 14
    ("19", "19 years old"),  # 14
    ("ad615d068e", "Namba Master"),  # 14
    ("princess", "Princess"),  # 14
    ("92a5bfbda2", "Nagae Style 40% Off Sale"),  # 14
    ("sex", "Morning Sex"),  # 14
    ("60483a8c81", "SLR"),  # 14
    ("av-open-2015-actress-category", "Av Open 2015 Actress Category"),  # 14
    ("bdd6ddecb7", "Fertilization"),  # 14
    ("168e962cc7", "5 ejaculations"),  # 14
    ("360356cc66", "Undisclosed"),  # 14
    ("68ef1e67bd", "genuine creampie"),  # 14
    ("av-open-2017-documentary-division", "Av Open 2017 Documentary Division"),  # 13
    ("79591548e5", "Crystal Video 40% Off Sale"),  # 13
    ("a009caa7d8", "sweat"),  # 13
    ("3151a87f89", "Kiss"),  # 13
    ("game-live-action", "Live-Action Game"),  # 13
    ("av-open-2016-hard-division", "Av Open 2016 Hard Division"),  # 13
    ("288b949695", "Bonus included"),  # 13
    ("6269f71c84", "2 consecutive shots"),  # 13
    ("av-open-2015-amateur-division", "Av Open 2015 Amateur Division"),  # 13
    ("av-open-2016-actress-category", "Av Open 2016 Actress Category"),  # 12
    ("9e5f956fbf", "Standing penis"),  # 12
    ("av-open-2017-drama-division", "Av Open 2017 Drama Division"),  # 12
    ("d174f2fa2f", "Potato"),  # 12
    ("74045258fb", "Pile driver"),  # 12
    ("40-1", "ナガエスタイル40%オフセール"),  # 12
    ("a9e3de41ce", "periscope"),  # 12
    ("73b3fb2c7b", "Erotic voice"),  # 12
    ("av-open-2017-mania-division", "Av Open 2017 Mania Division"),  # 12
    ("with-benefits-av-baseball", "Bonus Available (Avbaseball)"),  # 12
    ("eros", "Eros"),  # 12
    ("psycho-thriller", "Psychological Thriller"),  # 12
    ("b193685f69", "Renrekomi"),  # 12
    ("7af2301034", "Hajirai"),  # 12
    ("e91247059d", "relationship"),  # 11
    ("e7a61bc461", "Divorced"),  # 11
    ("ad7c62202d", "Gap"),  # 11
    ("fb3e1c40c2", "Black Stockings"),  # 11
    ("a8a35b28c7", "The cutest"),  # 11
    ("9ae6a51d56", "bathroom"),  # 11
    ("4ff0077a46", "Adult"),  # 11
    ("caffa39254", "Double Peace"),  # 11
    ("447f9b7430", "Glamorous"),  # 11
    ("188ac4f9d0", "Sexy underwear"),  # 11
    ("63d62e674c", "Nokezori"),  # 11
    ("bb707bbfd7", "Vibe (the one that sucks)"),  # 11
    ("517f59875f", "Full body fishnet tights"),  # 11
    ("45f6bdf642", "swimming club"),  # 11
    ("anime", "Anime"),  # 11
    ("fd8dfe8caa", "Small face"),  # 11
    ("68f8697c8c", "Kitchen"),  # 11
    ("bb1ee8eb76", "Small pussy"),  # 11
    ("m-2", "Masochist"),  # 11
    ("981d556942", "Beautiful body"),  # 11
    ("c6ae14637d", "Pure"),  # 11
    ("a6dc80113e", "Game"),  # 11
    ("tiktok", "Tiktok"),  # 11
]

GIDX = dict((s, n) for s, n in GENRES)

# ---------------------------------------------------------------- 工具

TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(s):
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", s or "")).strip()


def unesc(s):
    if not s:
        return ""
    return (s.replace("&#039;", "'").replace("&#39;", "'")
             .replace("&quot;", '"').replace("&amp;", "&")
             .replace("&lt;", "<").replace("&gt;", ">")
             .replace("&nbsp;", " ").replace("&#8217;", "'"))


def unesc_js(s):
    """Alpine 内联 JSON 的转义还原"""
    if not s:
        return ""
    return (s.replace("\\u0022", '"').replace("\\u0027", "'")
             .replace("\\u0026", "&").replace("\\/", "/"))


def to_int(s):
    try:
        return int(re.sub(r"[^\d]", "", str(s)) or 0)
    except Exception:
        return 0


def q(s):
    return urllib.parse.quote(str(s or ""), safe="")


# ---------------------------------------------------------------- HTTP

class _HTTP(object):
    """标准库 HTTP 层(带重试 / 可选代理)"""

    def __init__(self, proxy=""):
        self.proxy = proxy or ""
        self._opener = None

    def _op(self):
        if self._opener is None:
            hs = []
            if self.proxy:
                hs.append(urllib.request.ProxyHandler(
                    {"http": self.proxy, "https": self.proxy}))
            self._opener = urllib.request.build_opener(*hs)
        return self._opener

    def get(self, url, referer="", tries=4, timeout=30):
        last = None
        for i in range(max(1, tries)):
            try:
                h = {
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "close",
                }
                if referer:
                    h["Referer"] = referer
                req = urllib.request.Request(url, headers=h)
                with self._op().open(req, timeout=timeout) as r:
                    return r.read().decode("utf-8", "ignore")
            except Exception as e:
                last = e
                if i < tries - 1:
                    time.sleep(0.8 * (i + 1) + random.random() * 0.4)
        raise last if last else RuntimeError("http fail")


# ---------------------------------------------------------------- 本机转发
# 站点对 m3u8 与每个分片都校验 Referer: https://javplayer.cc/
# 壳不一定把 header 带下来 → 由源在本机起只读转发,自己补 Referer 再给壳。
# 全程只读(只做 GET),地址走 base64url,端口随机、只绑 127.0.0.1、随进程退出。

RELAY_ON = True                       # 本地转发总开关(False → 全部走直链 + header)
RELAY_DIRECT_LINE = True              # 播放列表里是否附带「·直链」备用线路
RELAY_HOST = "127.0.0.1"
_RELAY_LOCK = threading.Lock()
_RELAY = {"port": 0}


def _b64e(s):
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _b64d(s):
    try:
        s = str(s or "")
        s += "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8", "ignore")
    except Exception:
        return ""


def _relay_open(u):
    req = urllib.request.Request(u, headers={
        "User-Agent": UA,
        "Referer": PLAYER_REF,
        "Origin": PLAYER_HOST,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    })
    return urllib.request.urlopen(req, timeout=25)


def _relay_rewrite(txt, base):
    """m3u8 里所有子清单 / 分片 / KEY / MAP 地址 → 全部改回本机转发"""
    out = []
    for ln in (txt or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            if 'URI="' in s:
                s = re.sub(r'URI="([^"]+)"',
                           lambda m: 'URI="%s"' % _relay_link(
                               urllib.parse.urljoin(base, m.group(1))), s)
            out.append(s)
        else:
            out.append(_relay_link(urllib.parse.urljoin(base, s)))
    return "\n".join(out) + "\n"


class _RelayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Accept-Ranges", "none")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except Exception:
            pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path not in ("/p", "/p.m3u8", "/p.ts"):
            return self._send(404, b"not found", "text/plain")
        target = _b64d((urllib.parse.parse_qs(p.query).get("u") or [""])[0])
        if not target.startswith("http"):
            return self._send(400, b"bad target", "text/plain")
        try:
            with _relay_open(target) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                data = r.read()
        except Exception:
            return self._send(502, b"upstream fail", "text/plain")
        if data[:7] == b"#EXTM3U" or "mpegurl" in ctype:
            body = _relay_rewrite(data.decode("utf-8", "ignore"), target)
            return self._send(200, body.encode("utf-8"),
                              "application/vnd.apple.mpegurl")
        if "vtt" in ctype or target.split("?")[0].endswith(".vtt"):
            return self._send(200, data, "text/vtt; charset=utf-8")
        return self._send(200, data, ctype or "video/mp2t")


def _relay_start():
    """起本机转发服务,返回端口;起不来返回 0(调用方回退直链)"""
    if _RELAY["port"]:
        return _RELAY["port"]
    if not RELAY_ON:
        return 0
    with _RELAY_LOCK:
        if _RELAY["port"]:
            return _RELAY["port"]
        try:
            class _Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
                daemon_threads = True
                allow_reuse_address = True

                def handle_error(self, *a):
                    pass

            srv = _Srv((RELAY_HOST, 0), _RelayHandler)
            _RELAY["port"] = int(srv.server_address[1])
            t = threading.Thread(target=srv.serve_forever)
            t.daemon = True
            t.start()
            _RELAY["srv"] = srv
        except Exception:
            _RELAY["port"] = 0
        return _RELAY["port"]


def _relay_link(u):
    port = _RELAY["port"] or _relay_start()
    if not port or not u:
        return u
    # 清单类带 .m3u8 后缀,部分壳靠后缀判定播放类型
    path = "/p.m3u8" if u.split("?")[0].lower().endswith(".m3u8") else "/p"
    return "http://%s:%d%s?u=%s" % (RELAY_HOST, port, path, _b64e(u))


def _relay_url(u):
    """播放位入口:能转发就转发,转发不可用则返回空(调用方回退直链)"""
    if not RELAY_ON or not u:
        return ""
    if _relay_start():
        return _relay_link(u)
    return ""


# ---------------------------------------------------------------- 解析

def parse_cards(html):
    """列表页作品卡片 → vod 列表"""
    out, seen = [], set()
    if not html:
        return out
    parts = html.split('<div class="card" ')[1:]
    for p in parts:
        chunk = p[:7000]
        m = re.search(r'<a class="card__cover" href="(/en/v/[^"]+)"', chunk)
        if not m:
            continue
        path = m.group(1).rstrip("/")
        slug = path.split("/")[-1]
        if not slug or slug in seen:
            continue
        seen.add(slug)
        img = re.search(r'<img class="card__img"[^>]*src="([^"]+)"', chunk)
        tit = re.search(r'<a class="card__link"[^>]*>(.*?)</a>', chunk, re.S)
        dur = re.search(r'<span class="card__dur">([^<]*)</span>', chunk)
        meta = re.search(r'<div class="card__meta">(.*?)</div>', chunk, re.S)
        when, views = "", ""
        if meta:
            spans = re.findall(r"<span[^>]*>(.*?)</span>", meta.group(1), re.S)
            txts = [strip_tags(x) for x in spans]
            txts = [x for x in txts if x]
            if txts:
                when = txts[0]
            if len(txts) > 1:
                views = txts[-1]
        name = unesc(strip_tags(tit.group(1))) if tit else slug.upper()
        mark = when or ""
        if dur and strip_tags(dur.group(1)) not in ("", "0:00"):
            mark = (strip_tags(dur.group(1)) + (" · " + mark if mark else ""))
        out.append({
            "vod_id": slug,
            "vod_name": name or slug.upper(),
            "vod_pic": unesc(img.group(1)) if img else "",
            "vod_remarks": mark,
        })
    return out


def parse_total(html):
    m = re.search(r'pagehead__count">([^<]*)<', html or "")
    return to_int(m.group(1)) if m else 0


def parse_last_page(html):
    m = re.search(r'href="[^"]*[?&]page=(\d+)"[^>]*rel="last"', html or "")
    if m:
        return to_int(m.group(1))
    m = re.search(r'page=(\d+)"\s*rel="last"', html or "")
    return to_int(m.group(1)) if m else 0


def parse_genre_chips(html):
    out = []
    for m in re.finditer(
            r'<a class="gchip" href="/en/genres/([a-z0-9\-]+)"[^>]*>\s*'
            r'<span class="gchip__name">([^<]*)</span>\s*'
            r'<span class="gchip__count">([^<]*)</span>', html or ""):
        out.append((m.group(1), unesc(strip_tags(m.group(2))), m.group(3).strip()))
    return out


def parse_stars(html):
    """演员 / 片商 / 系列 条目 → 合集型 vod"""
    out, seen = [], set()
    if not html:
        return out
    # 演员
    for m in re.finditer(
            r'<div class="actress">\s*<a class="actress__avatar" href="/en/actresses/([^"]+)"'
            r'(?:[^>]*background-image:url\(\'([^\']*)\'\))?[^>]*>', html):
        slug, pic = m.group(1), m.group(2) or ""
        if slug in seen:
            continue
        seen.add(slug)
        seg = html[m.start():m.start() + 1600]
        n = re.search(r'<a class="actress__name"[^>]*>(.*?)</a>', seg, re.S)
        cnt = re.search(r'actress__count[^>]*>(.*?)<', seg, re.S)
        out.append({
            "vod_id": "a:" + slug,
            "vod_name": unesc(strip_tags(n.group(1))) if n else slug,
            "vod_pic": unesc(pic),
            "vod_remarks": (strip_tags(cnt.group(1)) + " 作品") if cnt else "演员",
        })
    if out:
        return out
    # 片商
    for m in re.finditer(r'<a class="mcard" href="/en/makers/([^"]+)">(.*?)</a>', html, re.S):
        slug, seg = m.group(1), m.group(2)[:1200]
        if slug in seen:
            continue
        seen.add(slug)
        n = re.search(r'<span class="mcard__name">(.*?)</span>', seg, re.S)
        c = re.search(r'<span class="mcard__meta">(.*?)</span>', seg, re.S)
        out.append({
            "vod_id": "m:" + slug,
            "vod_name": unesc(strip_tags(n.group(1))) if n else slug,
            "vod_pic": "",
            "vod_remarks": unesc(strip_tags(c.group(1))) if c else "片商",
        })
    if out:
        return out
    # 系列
    for m in re.finditer(r'<a class="srow" href="/en/series/([^"]+)">(.*?)</a>', html, re.S):
        slug, seg = m.group(1), m.group(2)[:1200]
        if slug in seen:
            continue
        seen.add(slug)
        n = re.search(r'<span class="srow__name">(.*?)</span>', seg, re.S)
        c = re.search(r'<span class="srow__meta">(.*?)</span>', seg, re.S)
        rk = re.search(r'<span class="srow__rank">(.*?)</span>', seg, re.S)
        out.append({
            "vod_id": "s:" + slug,
            "vod_name": unesc(strip_tags(n.group(1))) if n else slug,
            "vod_pic": "",
            "vod_remarks": unesc(strip_tags(c.group(1))) if c else (strip_tags(rk.group(1)) if rk else "系列"),
        })
    return out


def parse_info_table(html):
    """详情页 dl.watch__info → {字段: (文本, [链接])}"""
    info = {}
    i = html.find('<dl class="watch__info">')
    if i < 0:
        return info
    seg = html[i:]
    j = seg.find("</dl>")
    if j > 0:
        seg = seg[:j]
    for m in re.finditer(r'<dt>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>', seg, re.S):
        key = strip_tags(m.group(1))
        val = unesc(strip_tags(m.group(2)))
        links = re.findall(r'href="([^"]+)"', m.group(2))
        if links:
            names = [unesc(strip_tags(x)) for x in
                     re.findall(r'<a[^>]*>(.*?)</a>', m.group(2), re.S)]
            val = " / ".join([x for x in names if x]) or val
        info[key] = (val, links)
    return info


def parse_episodes(html):
    """详情页 Alpine player 配置 → (剧集列表, 数字id, slug, rec基址, token)"""
    m = re.search(
        r"player\(JSON\.parse\('(.*?)'\),\s*(\d+),\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)",
        html or "", re.S)
    if not m:
        return [], "", "", "", ""
    eps = []
    try:
        eps = json.loads(unesc_js(m.group(1)))
    except Exception:
        eps = []
    if not isinstance(eps, list):
        eps = []
    return eps, m.group(2), m.group(3), unesc_js(m.group(4)), m.group(5)


def ep_hash(url):
    m = re.search(r"javplayer\.cc/e/([A-Za-z0-9_]+)", url or "")
    return m.group(1) if m else ""


def parse_cover(html, slug=""):
    m = re.search(r'<meta property="og:image" content="([^"]+)"', html or "")
    if m:
        return unesc(m.group(1))
    m = re.search(r'<div class="player"[^>]*background-image:url\(\'([^\']+)\'\)', html or "")
    if m:
        return unesc(m.group(1))
    if slug:
        return "https://icdn.123av.me/img2/s500/%s/%s/cover.jpg" % (slug[:2], slug)
    return ""


def parse_related(html):
    out = []
    i = html.find('<ul class="watch-side__list">')
    if i < 0:
        return out
    seg = html[i:i + 60000]
    for m in re.finditer(r'<a class="vside" href="/en/v/([^"]+)"(.*?)(?=<a class="vside"|</ul>)', seg, re.S):
        slug, body = m.group(1), m.group(2)
        t = re.search(r'<span class="vside__title">(.*?)</span>', body, re.S)
        if t:
            out.append(slug)
    return out


# ---------------------------------------------------------------- 主类

class Spider(_Base):

    def __init__(self):
        self._http = None
        self.cfg = {}
        self._pc = {}          # 分页总数缓存 {path: pages}
        self._det = {}         # 详情缓存 {slug: (html, ts)}
        self._stream = {}      # 播放缓存 {hash: (url, ts)}
        self._CACHE_MAX = 120

    # ------------------------------------------------ 壳约定
    def getName(self):
        return "123AV"

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4)(\?|$)", url or ""))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def init(self, extend=""):
        cfg = {}
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else dict(extend)
            except Exception:
                for kv in str(extend).split("&"):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        cfg[k.strip()] = v.strip()
        if not isinstance(cfg, dict):
            cfg = {}
        self.cfg = cfg
        self._http = _HTTP(cfg.get("proxy", ""))

    def http(self):
        if self._http is None:
            self.init("")
        return self._http

    def get(self, url, referer=""):
        return self.http().get(url, referer=referer)

    def _cache_put(self, d, k, v):
        if len(d) >= self._CACHE_MAX:
            try:
                d.pop(next(iter(d)))
            except Exception:
                d.clear()
        d[k] = v

    # ------------------------------------------------ 路径 / 参数

    def _path_of(self, tid, ext):
        tid = str(tid or "").strip()
        if tid.startswith("g:"):
            return "/en/genres/" + q(tid[2:])
        if tid.startswith("a:"):
            return "/en/actresses/" + q(tid[2:])
        if tid.startswith("m:"):
            return "/en/makers/" + q(tid[2:])
        if tid.startswith("s:"):
            return "/en/series/" + q(tid[2:])
        if tid.startswith("t:"):
            return "/en/tags/" + q(tid[2:])
        # 类型筛选(在一级固定/维度分类下选类型 → 切到类型页)
        g = (ext or {}).get("genre", "") if isinstance(ext, dict) else ""
        if g:
            return "/en/genres/" + q(g)
        for k, _n, p in FIXED:
            if k == tid:
                return p
        for k, _n, p, _m in DIMS:
            if k == tid:
                return p
        return "/en/new"

    def _build_url(self, path, pg, ext):
        params = []
        if isinstance(ext, dict):
            for key, qk in (("type", "type"), ("year", "year"),
                            ("actress", "actress"), ("sort", "sort")):
                v = str(ext.get(key, "") or "").strip()
                if v:
                    params.append((qk, v))
        if pg and int(pg) > 1:
            params.append(("page", str(int(pg))))
        if not params:
            return HOST + path
        sep = "&" if "?" in path else "?"
        return HOST + path + sep + urllib.parse.urlencode(params)

    # ------------------------------------------------ 首页

    def homeContent(self, filter):
        try:
            classes = [{"type_id": k, "type_name": n} for k, n, _p in FIXED]
            classes.append({"type_id": "g:all", "type_name": "类型(%d)" % len(GENRES)})
            classes += [{"type_id": k, "type_name": n} for k, n, _p, _m in DIMS]
            gval = [{"n": "全部", "v": ""}] + [{"n": n, "v": s} for s, n in GENRES]
            f_type = [{"n": n, "v": v} for v, n in TYPES]
            f_act = [{"n": n, "v": v} for v, n in ACTRESS_F]
            f_sort = [{"n": n, "v": v} for v, n in SORTS]
            f_year = [{"n": ("全部" if v == "" else v), "v": v} for v in YEARS]
            filters = {
                "g:all": [{"key": "genre", "name": "类型", "value": gval}],
            }
            for k, _n, _p in FIXED:
                filters[k] = [
                    {"key": "genre", "name": "类型", "value": gval},
                    {"key": "type", "name": "分类", "value": f_type},
                    {"key": "year", "name": "年份", "value": f_year},
                    {"key": "actress", "name": "女优数", "value": f_act},
                    {"key": "sort", "name": "排序", "value": f_sort},
                ]
            for k, _n, _p, _m in DIMS:
                filters[k] = [
                    {"key": "type", "name": "分类", "value": f_type},
                    {"key": "year", "name": "年份", "value": f_year},
                    {"key": "actress", "name": "女优数", "value": f_act},
                    {"key": "sort", "name": "排序", "value": f_sort},
                ]
            return {"class": classes, "filters": filters}
        except Exception:
            return {"class": [], "filters": {}}

    def homeVideoContent(self):
        try:
            return {"list": parse_cards(self.get(HOST + "/en/new"))}
        except Exception:
            return {"list": []}

    # ------------------------------------------------ 分类

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            if pg < 1:
                pg = 1
            tid = str(tid or "").strip()
            ext = extend if isinstance(extend, dict) else {}
            path = self._path_of(tid, ext)
            # 类型总入口未选类型时 → 走最新列表
            if tid == "g:all" and not ext.get("genre"):
                path = "/en/new"
            url = self._build_url(path, pg, ext)
            html = self.get(url)

            mode = "list"
            for k, _n, _p, m in DIMS:
                if tid == k:
                    mode = m
            if tid.startswith(("a:", "m:", "s:", "t:")):
                mode = "list"

            if mode == "star":
                vlist = parse_stars(html)
            else:
                vlist = parse_cards(html)
                if not vlist and pg == 1:
                    vlist = parse_stars(html)

            total = parse_total(html)
            pages = parse_last_page(html)
            if pages:
                self._cache_put(self._pc, path, pages)
            else:
                pages = self._pc.get(path, 0)
            if not pages:
                pages = MAX_PAGE_FALLBACK
            if not total:
                total = len(vlist)

            return {
                "list": vlist,
                "page": pg,
                "pagecount": max(1, pages),
                "limit": PER_PAGE,
                "total": total,
            }
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": PER_PAGE, "total": 0}

    # ------------------------------------------------ 详情

    def _detail_html(self, slug):
        c = self._det.get(slug)
        now = time.time()
        if c and now - c[1] < 300:
            return c[0]
        html = self.get(HOST + "/en/v/" + slug)
        self._cache_put(self._det, slug, (html, now))
        return html

    def detailContent(self, ids):
        try:
            vid = ids[0] if isinstance(ids, (list, tuple)) else ids
            vid = str(vid or "").strip()
            if not vid:
                return {"list": []}

            # 合集:演员 / 片商 / 系列
            if vid.startswith(("a:", "m:", "s:")):
                return {"list": [self._collection(vid)]}

            slug = vid
            for pre in ("123av://", "v:"):
                if slug.startswith(pre):
                    slug = slug[len(pre):]
            slug = slug.strip("/")
            if "/" in slug:
                slug = slug.split("/")[-1]

            html = self._detail_html(slug)
            info = parse_info_table(html)
            eps, num_id, cfg_slug, rec, tok = parse_episodes(html)

            tit = re.search(r'<h1 class="watch__title"[^>]*>(.*?)</h1>', html, re.S)
            title = unesc(strip_tags(tit.group(1))) if tit else slug.upper()

            desc = ""
            m = re.search(r'<div class="watch__desc"[^>]*>(.*?)</div>\s*(?:<button|</section>)',
                          html, re.S)
            if m:
                desc = unesc(strip_tags(m.group(1)))
            if not desc:
                m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
                desc = unesc(m.group(1)) if m else ""

            cover = parse_cover(html, slug)

            code = info.get("Code", ("", []))[0] or slug.upper()
            casts = info.get("Cast", ("", []))[0]
            maker = info.get("Maker", ("", []))[0]
            series = info.get("Series", ("", []))[0]
            genres = info.get("Genres", ("", []))[0]
            tags = info.get("Tags", ("", []))[0]
            types = info.get("Type", ("", []))[0]
            rdate = info.get("Release date", ("", []))[0]

            lines = []
            if code:
                lines.append("番号: %s" % code)
            if title and title.upper().startswith(code.upper()):
                lines.append("标题: %s" % title)
            if rdate:
                lines.append("发行日期: %s" % rdate)
            if types:
                lines.append("分类: %s" % types)
            if casts:
                lines.append("演员: %s" % casts)
            if maker:
                lines.append("片商: %s" % maker)
            if series:
                lines.append("系列: %s" % series)
            if genres:
                lines.append("类型: %s" % genres)
            if tags:
                lines.append("标签: %s" % tags)
            lines.append("播放来源: javplayer 直链")

            # 播放列表:多集 → 多线路;兜底用页面 slug 反查
            plays = []
            for i, ep in enumerate(eps or []):
                h = ep_hash(unesc_js(ep.get("url", "")))
                if not h:
                    continue
                nm = ep.get("name") or ("第 %d 集" % (i + 1))
                plays.append("%s$123av://%s" % (nm, h))
                if RELAY_DIRECT_LINE:
                    plays.append("%s·直链$123av://%s|direct" % (nm, h))
            if not plays:
                plays.append("正片$123av://slug:%s" % slug)

            rel = parse_related(html)
            if rel:
                lines.append("相关: %s" % ", ".join([x.upper() for x in rel[:8]]))

            return {"list": [{
                "vod_id": slug,
                "vod_name": title or code,
                "vod_pic": cover,
                "vod_remarks": ((rdate + " · ") if rdate else "") + (types or ""),
                "vod_year": (rdate[:4] if rdate else ""),
                "vod_area": "日本",
                "vod_actor": casts,
                "vod_director": maker,
                "vod_content": "\n".join(lines) + ("\n\n简介: " + desc if desc else ""),
                "vod_play_from": "123AV",
                "vod_play_url": "#".join(plays),
                "type_name": genres,
            }]}
        except Exception:
            return {"list": []}

    def _collection(self, vid):
        """演员 / 片商 / 系列 → 合集条目(作品列表即为播放列表)"""
        kind, slug = vid[0], vid[2:]
        base = {"a": ("/en/actresses/", "演员", "a"),
                "m": ("/en/makers/", "片商", "m"),
                "s": ("/en/series/", "系列", "s")}[kind]
        name = slug
        pic = ""
        total = 0
        plays = []
        info_txt = []
        try:
            html = self.get(HOST + base[0] + slug)
            h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            if h1:
                name = unesc(strip_tags(h1.group(1))) or slug
            total = parse_total(html)
            if kind == "a":
                m = re.search(r"background-image:url\('([^']+)'\)", html)
                pic = unesc(m.group(1)) if m else ""
                st = re.search(r'class="astat[^"]*">(.*?)</div>', html, re.S)
                if st:
                    info_txt.append(unesc(strip_tags(st.group(1))))
            cards = parse_cards(html)
            for c in cards:
                plays.append("%s$123av://slug:%s" % (c["vod_name"][:60], c["vod_id"]))
            if not info_txt:
                info_txt.append("%s · 收录 %d 部" % (base[1], total or len(cards)))
        except Exception:
            pass
        if not plays:
            plays.append("查看$123av://slug:" + slug)
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": "%s · %s 部" % (base[1], total) if total else base[1],
            "vod_content": "\n".join(info_txt),
            "vod_play_from": "123AV",
            "vod_play_url": "#".join(plays),
        }

    # ------------------------------------------------ 搜索

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            kw = str(key or "").strip()
            if not kw:
                return {"list": [], "page": 1, "pagecount": 1, "limit": PER_PAGE, "total": 0}
            url = HOST + "/en/search?keyword=" + q(kw)
            if pg > 1:
                url += "&page=%d" % pg
            html = self.get(url)
            vlist = parse_cards(html)
            total = parse_total(html)
            pages = parse_last_page(html)
            if pages:
                self._cache_put(self._pc, "search:" + kw, pages)
            else:
                pages = self._pc.get("search:" + kw, 0)
            if not pages:
                pages = max(1, (total + PER_PAGE - 1) // PER_PAGE) if total else 1
            if not total:
                total = len(vlist)
            return {"list": vlist, "page": pg, "pagecount": max(1, pages),
                    "limit": PER_PAGE, "total": total}
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": PER_PAGE, "total": 0}

    # ------------------------------------------------ 播放

    def _stream_of(self, h):
        c = self._stream.get(h)
        now = time.time()
        if c and now - c[1] < 1800:
            return c[0]
        js = self.get(PLAYER_HOST + "/stream?id=" + q(h),
                      referer=PLAYER_HOST + "/e/" + h)
        m = re.search(r'"stream"\s*:\s*"([^"]+)"', js or "")
        url = unesc_js(m.group(1)) if m else ""
        if not url:
            try:
                j = json.loads(js)
                url = ((j.get("media") or {}).get("stream") or "")
            except Exception:
                url = ""
        if url:
            self._cache_put(self._stream, h, (url, now))
        return url

    def _mk_play(self, u, flag, direct=False):
        """direct=False → 本机转发(壳不必认 header,Referer 由源补齐)
           direct=True  → 直链 + 老格式 header(给认得 header 的壳)"""
        if not direct:
            pu = _relay_url(u)
            if pu:
                return {"parse": 0, "playUrl": "", "url": pu, "flag": flag}
        return {"parse": 0, "playUrl": "", "url": u,
                "header": "User-Agent@%s&Referer@%s" % (UA, PLAYER_REF),
                "flag": flag}

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        for pre in ("123av://",):
            if raw.startswith(pre):
                raw = raw[len(pre):]
        direct = False
        if raw.endswith("|direct"):
            direct = True
            raw = raw[:-7]
        try:
            # 作品 slug → 先抓详情页取真流 hash
            if raw.startswith("slug:"):
                slug = raw[5:].strip()
                html = self._detail_html(slug)
                eps, _n, _s, _r, _t = parse_episodes(html)
                for ep in (eps or []):
                    h = ep_hash(unesc_js(ep.get("url", "")))
                    if h:
                        u = self._stream_of(h)
                        if u:
                            return self._mk_play(u, flag, direct)
                return {"parse": 1, "playUrl": "",
                        "url": HOST + "/en/v/" + slug, "flag": flag}

            h = raw
            # 拿到的是完整 javplayer 页 → 提 hash
            if "javplayer.cc/e/" in h:
                h = ep_hash(h)
            # 拿到的是作品页路径 → 走上面那条
            if not h or "/" in h:
                if h:
                    slug = h.rstrip("/").split("/")[-1]
                    return self.playerContent(flag, "slug:" + slug, vipFlags)
                return {"parse": 1, "playUrl": "", "url": str(id), "flag": flag}

            u = self._stream_of(h)
            if u:
                return self._mk_play(u, flag, direct)
            # 兜底:回退嵌入页,交给壳内解析
            return {"parse": 1, "playUrl": "",
                    "url": PLAYER_HOST + "/e/" + h, "flag": flag}
        except Exception:
            return {"parse": 1, "playUrl": "", "url": str(id), "flag": flag}
