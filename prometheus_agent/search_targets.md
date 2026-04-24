# search_targets — порядок обхода: Tier 1 → 2 → 3 → 4 (сверху вниз). Не переставлять блоки.
#
# Правила (v2 / skill):
# - Tier 1–3: каждая ссылка — прямой визит; недоступна → фиксировать в логе, продолжать.
# - Tier 4: целевой поиск «"Product Manager" OR "Product Lead" remote EU» на платформах (в script_crawl пока только входные URL; полный поиск — отдельный модуль).
# - We Work Remotely (weworkremotely.com) — исключена (домен режется в коде).
# - Вакансии ≤5 дней: если дата не извлечена — в details будет date_unknown (⚠️ для отчёта).
#
# Строки с «Tier: …» задают tier; URL в строке таблицы или отдельной строке подхватываются автоматически.
# Tier4 search (пока только маркер для отчёта / следующего модуля)
# QUERY: "Product Manager" OR "Product Lead" remote EU

Tier: 1
https://telegram.org/jobs  # Telegram
https://miro.com/careers/  # Miro
https://www.jetbrains.com/jobs/  # JetBrains
https://careers.veeam.com/  # Veeam
https://www.wrike.com/careers/  # Wrike
https://www.tradingview.com/careers/  # TradingView
https://badoo.com/en/the-company  # Badoo
https://jobs.indrive.com/  # inDrive
https://playrix.com/job/openings  # Playrix
https://nexters.com/careers  # Nexters
https://gcore.com/careers  # Gcore
https://careers.semrush.com/  # Semrush
https://prisma-ai.com/  # Prisma Labs
https://manychat.com/careers  # Manychat
https://finom.co/en/careers/  # Finom
https://endel.io/careers  # Endel
https://www.novakidschool.com/careers/  # Novakid
https://anna.money/careers  # ANNA Money
https://marine-digital.com/  # Marine Digital
https://crypterium.com/  # Crypterium
https://humaniq.com/  # Humaniq
https://www.immigram.io/  # Immigram
https://studyfree.com/  # StudyFree
https://bioniq.com/careers  # Bioniq
https://adapty.io/careers/  # Adapty
https://qdrant.tech/careers/  # Qdrant
https://clickhouse.com/company/careers  # ClickHouse
https://nebius.com/careers  # Nebius
https://toloka.ai/careers  # Toloka
https://www.avride.ai/career  # Avride
https://wheely.com/en/careers  # Wheely
https://softlineglobal.com/careers  # Softline
https://www.dataart.com/career  # DataArt
https://career.luxoft.com/  # Luxoft
https://www.epam.com/careers  # EPAM Systems
https://www.griddynamics.com/careers  # Grid Dynamics
https://devexperts.com/jobs/  # Devexperts
https://exactpro.com/career  # Exactpro
https://bookmate.com/  # Bookmate
https://dodo.dev/  # Dodo Brands
https://skyeng.ru/  # Skyeng
https://xsolla.com/careers  # Xsolla
https://www.joom.com/en/careers  # Joom
https://bumble.com/en/the-buzz/tag/careers  # Bumble
https://careers.kaspersky.com/  # Kaspersky
https://www.group-ib.com/careers/  # Group-IB
https://www.ptsecurity.com/ww-en/company/careers/  # Positive Technologies
https://ibsgroup.com/  # IBS Group
https://easybrain.com/careers  # Easybrain
https://www.dashabot.io/careers  # Dasha AI
https://tripleten.com/careers/  # TripleTen
https://mubert.com/jobs  # Mubert
https://www.faceapp.com/  # Wireless Lab FaceApp
https://grabr.io/  # Grabr
https://www.recraft.ai/  # Recraft
https://praktika.ai/  # Praktika.ai
https://osome.com/careers/  # Osome
https://spatial.chat/  # SpatialChat
https://amixr.io/  # Amixr
https://www.jiffy-app.com/  # Jiffy
https://b2broker.com/company/careers/  # B2BROKER
https://flo.health/careers  # Flo Health
https://qonversion.io/careers  # Qonversion
https://www.maroo.us/  # Maroo
https://ebaconline.com.br/  # EBAC Online
https://www.netris.ai/  # Netris
https://www.appintheair.com/  # App in the Air

Tier: 2
https://www.revolut.com/careers/  # Revolut
https://www.pandadoc.com/careers/  # PandaDoc
https://bumble.com/en/the-buzz/tag/careers  # Bumble (дубликат URL из таблицы Tier 2)
https://cast.ai/careers/  # CAST AI
https://compasspathways.com/join-us/  # Compass Pathways
https://kewazo.com/careers/  # Kewazo
https://ifarm.fi/  # iFarm
https://www.personio.com/about-personio/careers/  # Personio
https://arrival.com/  # Arrival
https://www.scentbird.com/careers  # Scentbird
https://prodly.co/  # Prodly
https://collectly.co/careers  # Collectly
https://neon.com/careers  # Neon
https://www.singlestore.com/company/careers/  # SingleStore
https://wargaming.com/en/careers  # Wargaming
https://jobs.ashbyhq.com/kraken.com  # Kraken Ashby

Tier: 3
https://ssi.inc/  # Safe Superintelligence
https://nearspacelabs.com/  # Near Space Labs
https://www.people.ai/company/careers  # People.ai
https://www.creatio.com/company/careers  # Creatio
https://www.airslate.com/careers  # airSlate
https://restream.io/careers  # Restream
https://reply.io/careers/  # Reply.io
https://reface.ai/  # Reface
https://careers.preply.com/  # Preply
https://www.grammarly.com/jobs  # Grammarly
https://about.gitlab.com/jobs/  # GitLab
https://jobs.lever.co/truv  # Truv
https://devzion.com/careers/  # Zion Development
https://inxy.io/careers/  # INXY
https://www.nozomihealth.com/  # Nozomi
https://medvidi.com/careers/  # MEDvidi
https://jobs.lever.co/appfollow  # AppFollow
https://remote.com/openings  # Remote
https://careers.bark.com/jobs  # Bark
https://appewa.com/  # EWA Lithium Lab
https://nove8.peopleforce.io/careers  # nove8
https://www.infomediji.si/careers/  # infomediji DeoVR
https://dwelly.group/careers/  # Dwelly
https://job-boards.greenhouse.io/dwelly  # Dwelly (Greenhouse)

Tier: 4
_TIER4_QUERY: "Product Manager" OR "Product Lead" remote EU
https://job-boards.greenhouse.io/  # Greenhouse boards
https://jobs.lever.co/  # Lever
https://jobs.ashbyhq.com/  # Ashby
https://apply.workable.com/  # Workable
https://www.linkedin.com/jobs/  # LinkedIn Jobs
https://wellfound.com/jobs  # Wellfound
https://www.welcometothejungle.com/en  # Welcome to the Jungle
https://www.indeed.com/  # Indeed
https://www.glassdoor.com/Job/  # Glassdoor
https://www.dice.com/jobs  # Dice
https://startup.jobs/  # startup.jobs
https://www.ycombinator.com/jobs  # Y Combinator
https://landing.jobs/  # Landing.Jobs
https://remoteok.com/  # Remote OK
https://remotive.com/remote-jobs  # Remotive
https://www.eu-startups.com/  # EU-Startups
https://builtin.com/jobs  # Built In
https://djinni.co/  # Djinni
https://career.habr.com/  # Habr Career
https://nofluffjobs.com/  # No Fluff Jobs
https://justjoin.it/  # Just Join IT
https://www.reed.co.uk/jobs  # Reed
https://www.totaljobs.com/  # Totaljobs
https://www.cv-library.co.uk/  # CV-Library
https://workinstartups.com/  # Work In Startups
https://www.stepstone.com/  # StepStone
https://www.xing.com/jobs  # XING Jobs
https://www.ziprecruiter.com/  # ZipRecruiter
https://www.monster.com/jobs  # Monster
https://cryptojobslist.com/  # CryptoJobsList
https://web3.career/  # Web3.career
https://relocate.me/  # Relocate.me
https://www.teamtailor.com/  # Teamtailor
https://jobs.smartrecruiters.com/  # SmartRecruiters
https://jobs.jobvite.com/  # Jobvite
https://www.jazzhr.com/  # JazzHR
https://join.com/  # JOIN
https://breezy.hr/  # Breezy HR
https://www.bamboohr.com/  # BambooHR
https://www.icims.com/  # iCIMS
https://www.workday.com/  # Workday
