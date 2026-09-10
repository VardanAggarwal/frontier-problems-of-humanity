<!-- CRAWL STATE — impact-network-crawler's handover between passes.
     Read by every crawl; appended to at the end of every pass.
     Leads, edges, prunes and dead ends accumulate here. A name listed as a
     DEAD END or PRUNED has already cost a search and must not be retried.
     Loader ignores `_`-prefixed files, so this never enters the corpus.
     Started as a /tmp scratch file during the Villgro crawl, 2026-09-10;

     LEAD HYGIENE (added 2026-09-11, after a pass lost its whole P1 to this):
     a LEAD is stale the moment the actor gets a record. Before seeding from any
     LEADS block, check problems/actors/<slug>.md exists; if it does, the lead is
     done. At the end of every pass, annotate every lead you wrote with
     `← WRITTEN: <slug> — retired from LEADS <date>` rather than only appending a
     new section. responsAbility, Skoll and IKEA sat in LEADS as "never written"
     for a day after they were written and committed.
     moved into the repo when that scratch directory went away. -->

## WRITTEN

- villgro — capacity-builder/funder/intermediary — tracked — LinkedIn @villgro-org (live) — India's oldest social-enterprise incubator, founded 2001
- srinivas-ramanujam — funder (individual) — tracked — LinkedIn linkedin.com/in/srinivas1729 (live) — Villgro CEO since 2019, ex-corporate
- paul-basil — funder (individual) — tracked — LinkedIn linkedin.com/in/paul-basil-73736a12 (live) — Villgro founder, now Menterra partner
- menterra — funder — tracked — LinkedIn menterra-venture-advisors (live) — Villgro's spun-out impact-investment fund, 2015
- shell-foundation — funder — tracked — X @ShellFoundation (live, 2026 posts) — Shell-funded charity, clean energy/livelihoods, ClimaFii Alliance
- villgro-africa — funder/intermediary — tracked — LinkedIn villgroafrica + CEO LinkedIn (live) — East African healthcare incubator, Villgro model replica
- ecozen-solutions — operator — registry — website+LinkedIn found, not deep-verified — Villgro's flagship portfolio exit, climate-smart deeptech
- lemelson-foundation — funder — tracked — website live, LinkedIn unconfirmed — US foundation, invention-based enterprise funder, India/Kenya
- doen-foundation — funder — tracked — website live, no social confirmed — Dutch lottery-funded green/social-enterprise foundation
- selco-foundation — field-builder/capacity-builder — tracked — LinkedIn+X live, 2026 posts confirmed — Harish Hande's decentralised-energy nonprofit, health-centre solarisation
- sankalp-forum — convener — tracked — LinkedIn+X live, 2026 event confirmed — Intellecap's flagship India/Global-South impact summit platform
- intellecap — intermediary/convener — tracked — website+LinkedIn(group) live — Aavishkaar Group's advisory arm, runs Sankalp Forum
- aavishkaar-group — funder — tracked — website+LinkedIn live — India's pioneering impact-investment platform, ~$1.4bn AUM
- northern-arc-capital — funder (debt) — tracked — website live, LinkedIn unconfirmed — listed debt platform for underbanked, ₹16,525cr AUM
- gray-matters-capital — funder — tracked — website live, LinkedIn unconfirmed — Global-South impact investor, women's edtech/skilling focus
- upaya-social-ventures — funder — tracked — website live, LinkedIn unconfirmed — Seattle/Bangalore seed investor, jobs-for-the-poorest model
- dasra — field-builder/convener/intermediary — tracked — LinkedIn live, 2026 posts confirmed — India's leading strategic-philanthropy systems orchestrator

Total: 17 actor files written, all complete (no half-written/invalid files).

## EDGES

- villgro --funded-by--> menterra (spun out as its own fund)
- villgro --funded-by--> shell-foundation
- villgro --funded-by--> lemelson-foundation
- villgro --funded-by--> doen-foundation
- villgro --board--> paul-basil (founder)
- villgro --board--> srinivas-ramanujam (CEO)
- villgro --spun-out-of--> villgro-africa (sister vehicle via IIEF/Paul Basil)
- villgro --cohort--> ecozen-solutions (portfolio, notable exit)
- menterra --funds--> iDreamCareer (co-invested with Gray Matters Capital, $1.63M seed)
- menterra --board--> paul-basil
- menterra --funded-by--> lemelson-foundation (seeded Fund I, ₹40cr, 2016)
- paul-basil --spun-out-of--> villgro-africa (IIEF replication vehicle)
- shell-foundation --co-funded--> accion (ClimaFii Alliance)
- shell-foundation --co-funded--> bfa-global (ClimaFii Alliance)
- shell-foundation --co-funded--> upaya-social-ventures (ClimaFii Alliance, ≥10 energy SMEs in India)
- shell-foundation --funds--> punjab-renewable-energy-systems (cited in existing monish-ahuja.md)
- villgro-africa --funded-by--> lemelson-foundation
- villgro-africa --funded-by--> auda-nepad
- villgro-africa --funded-by--> johnson-and-johnson-foundation
- villgro-africa --funded-by--> boehringer-ingelheim-social-engagement
- villgro-africa --convenes--> transforming-african-medtech-conference (CEO chaired 2025)
- villgro-africa --attends--> sankalp-africa-summit
- ecozen-solutions --funded-by--> northern-arc-capital (debt round Jan 2025)
- ecozen-solutions --funded-by--> responsability-investments (debt round Jan 2025)
- ecozen-solutions --funded-by--> triodos-investment-management
- ecozen-solutions --funded-by--> spark-capital (debt, Nov 2025)
- ecozen-solutions --funded-by--> uti-asset-management
- ecozen-solutions --funded-by--> dare-ventures (Series C first tranche)
- ecozen-solutions --funded-by--> maanaveeya-development-and-finance
- lemelson-foundation --funds--> selco-foundation
- lemelson-foundation --funds--> villgro-africa
- doen-foundation --funds--> selco-foundation
- doen-foundation --funds--> frontier-markets
- doen-foundation --funds--> bboxx (East Africa)
- doen-foundation --funds--> sunfunder (East Africa)
- selco-foundation --co-funded--> ikea-foundation (Energy for Health programme, 25,000 health centres by 2026/27)
- selco-foundation --convenes--> energy-for-health-programme (with Ministry of Health and Family Welfare, State Health Missions)
- selco-foundation --attends--> skoll-world-forum (2026, with Dasra and Antarang Foundation, Northeast India panel)
- selco-foundation --co-funded--> mizoram-department-of-agriculture (MoU, March 2026)
- sankalp-forum --parent--> intellecap (runs it)
- intellecap --parent--> aavishkaar-group (advisory arm of)
- northern-arc-capital --funded-by--> calvert-impact-capital (US$10M ECB financing)
- gray-matters-capital --co-funded--> menterra (iDreamCareer)
- gray-matters-capital --funds--> ufaber (₹25cr Series A, led)
- gray-matters-capital --funds--> thinkzone
- gray-matters-capital --funds--> indian-school-finance-company
- upaya-social-ventures --funded-by--> shell-foundation (ClimaFii Alliance partner)
- upaya-social-ventures --funds--> biofics-organics (2025, first-time)
- upaya-social-ventures --funds--> bintix (2025, follow-on)
- dasra --convenes--> dasra-philanthropy-week
- dasra --convenes--> india-philanthropy-forum (formerly Dasra Philanthropy Forum; London/NY/Mumbai 2026 editions)
- dasra --attends--> skoll-world-forum (2026, with Antarang Foundation and SELCO Foundation)
- dasra --publishes--> india-philanthropy-report (with Bain & Company, annual, 2026 edition on family-business philanthropy)
- responsability-investments --funds--> sahyadri-farms-post-harvest-care (Jan 2025)
- responsability-investments --funds--> wheelsemi ($10M, EV/two-wheeler financing)
- responsability-investments --funds--> ampin-energy-transition ($35M, renewable C&I developer)
- responsability-investments --funds--> ace-international-limited (with FMO, Dec 2025)
- responsability-investments --funds--> roserve-enviro (up to $25M, Jan 2026, Mumbai wastewater treatment)
- responsability-investments --funds--> qul-fruitwall (climate-resilient horticulture, Himalayan food system)
- skoll-foundation --funds--> indus-action (2026 Skoll Award for Social Innovation winner, India civic-tech/benefits-access)

## LEADS — unresearched, next-wave seed set

- Srinivas Ramanujam's prior corporate employer — edge: spun-out-of, from Villgro record — seen in bio ("15+ years corporate sector") but employer not named in sources pulled — worth naming for the spun-out-of edge.
- Villgro board members (Ashwin Mahalingam, Bharti Gupta Ramola, Dimple Gujral, Indumathi Nambi, Kairas Vakharia, Ranjeev Lodha, Sameer Mehta) — edge: board, from villgro.org/our-team — each is a named individual with an outside institutional seat (IIT-Madras, ex-PwC/Basix, Teach For India, Mahindra Farm Equipment, Dr Mehta's Hospitals) — high value as cross-sector bridges, not yet researched.  ← WRITTEN: bharti-gupta-ramola, dimple-gujral, indumathi-nambi, kairas-vakharia, ranjeev-lodha, sameer-mehta — retired from LEADS 2026-09-11
- Radhika Ramesh, Shelly Kwatra, Shriyam Yagnik, Aditi Pareek — Villgro COO and Impact Finance analyst team — edge: board/team, from villgro.org/our-team — programme-officer-level, likely higher-signal feeds than the CEO per the "mover over the money" bias — not yet researched.
- Vahan — edge: cohort, from Villgro seed (named as notable portfolio alongside Ecozen/Wysa in Tracxn summary) — gig-worker staffing platform — worth a wave, pushed to leads under old brief's "don't over-write operators" rule.  ← WRITTEN: vahan — retired from LEADS 2026-09-11
- Wysa — edge: cohort, from Villgro seed (same Tracxn line) — mental-health app, notable portfolio — pushed to leads, same reason.  ← WRITTEN: wysa — retired from LEADS 2026-09-11
- Vindya M Narsian — edge: co-funded, from Villgro's "$170K seed round in Avni Wellness, Oct 24 2025" (Tracxn) — named co-investor alongside IRMA — not researched.
- IRMA (Institute of Rural Management Anand) — edge: co-funded, same Avni Wellness round — an institution co-investing alongside Villgro, worth checking if it has a broader impact-capital role.
- Avni Wellness — edge: funded-by villgro (latest investment, $170K seed, Oct 2025) — not researched, portfolio company.
- Accion — edge: co-funded (ClimaFii Alliance), from shell-foundation — large global microfinance/fintech intermediary funding into India and Africa — high-value convener/intermediary, not researched this pass.  ← WRITTEN: accion — retired from LEADS 2026-09-11
- BFA Global — edge: co-funded (ClimaFii Alliance), from shell-foundation — fintech-for-inclusion research/advisory intermediary — not researched.  ← WRITTEN: bfa-global — retired from LEADS 2026-09-11
- Wilfred Njagi (individual) — edge: board/CEO, from villgro-africa — co-founder & CEO, active LinkedIn presence referencing Sankalp Africa Summit and WEF Davos 2026 — record not made (only org-level villgro-africa written); worth its own individual file per the "mover over the money" rule.  ← WRITTEN: wilfred-njagi — retired from LEADS 2026-09-11
- Dr Robert Karanja — edge: board (former CEO), from villgro-africa — handed CEO baton to Njagi — not researched, may still be active in the sector.
- AUDA-NEPAD — edge: funded-by, from villgro-africa — African Union Development Agency, continental institutional funder — global/African relevance to India is low; noted as African-context lead only.
- Johnson & Johnson Foundation — edge: funded-by, from villgro-africa — global corporate foundation — check India relevance before writing.
- Boehringer Ingelheim Social Engagement (BISE) — edge: funded-by, from villgro-africa — same caveat as J&J.
- Transforming African Medtech Conference (TAMC) — edge: convenes, from villgro-africa (CEO chaired 2025/2026) — African medtech convener, India relevance untested.
- Sankalp Africa Summit — edge: attends, from villgro-africa — sister event to Sankalp Global Summit (India) — already noted under sankalp-forum but the Africa edition itself not separately profiled.
- Vineet Rai (individual, Aavishkaar Group founder/Vice Chairman) — edge: board, from aavishkaar-group / intellecap — named but not channel-verified or written up — high-value "mover over letterhead" candidate.
- Vineet Chandra Rai (individual, Aavishkaar Group CEO) — same edge/source as above — not researched.
- Vikas Bali (individual, Intellecap CEO) — edge: board, from intellecap — not channel-verified.
- Calvert Impact Capital — edge: funded-by (of Northern Arc Capital, $10M ECB financing) — major US-based impact-capital intermediary active in India debt markets — not researched, high-value funder/intermediary.  ← WRITTEN: calvert-impact-capital — retired from LEADS 2026-09-11
- Triodos Investment Management — edge: funded-by (of Ecozen), also a global impact-investment bank active across India renewables/agri — not researched, recurring name worth a file.  ← WRITTEN: triodos-investment-management — retired from LEADS 2026-09-11
- Spark Capital — edge: funded-by (of Ecozen, Nov 2025 debt round) — India-based VC, check if impact-oriented enough for segment scope.
- UTI Asset Management Company — edge: funded-by (of Ecozen) — mainstream AMC dipping into climate debt; check India relevance/segment fit before writing.
- Dare Ventures — edge: funded-by (of Ecozen, Series C first tranche) — not researched.
- Frontier Markets — edge: funded-by (DOEN), from doen-foundation — well-known India last-mile rural distribution enterprise (women-led "Saral Jeevan" agent network) — high signal, not researched.  ← WRITTEN: frontier-markets — retired from LEADS 2026-09-11
- BBOXX, SunFunder — edge: funded-by (DOEN) — East Africa energy enterprises, lower India relevance — Africa-context leads only.
- IKEA Foundation — edge: co-funded, from selco-foundation (Energy for Health, Sustain Plus Platform, GIZ partnership) — major global climate/livelihoods funder into India, narrowed its climate strategy in 2025 — high-value funder, not written up as its own file this pass (only cited inline on selco-foundation.md).  ← WRITTEN: ikea-foundation — retired from LEADS 2026-09-11
- Sustain Plus Energy Foundation — edge: co-funded (IKEA Foundation partner, India renewable-energy platform, 150+ partners) — not researched, high-value India intermediary/platform.  ← WRITTEN: sustain-plus-energy-foundation — retired from LEADS 2026-09-11
- GIZ (India) — edge: co-funded (IKEA Foundation partnership, smallholder farmer decentralised energy) — German development agency, institutional funder — not researched.
- Dasra, Antarang Foundation — edge: attends, from selco-foundation's Skoll World Forum 2026 panel — Dasra was subsequently written up; Antarang Foundation (skilling/livelihoods nonprofit) was not — worth a wave.  ← WRITTEN: dasra, antarang-foundation — retired from LEADS 2026-09-11
- Ministry of Health and Family Welfare / State Health Missions — edge: convenes (with selco-foundation, Energy for Health) — institutional, likely registry-depth only.
- Mizoram Department of Agriculture — edge: co-funded (MoU with SELCO, March 2026) — state-government institutional actor, registry-depth candidate only.
- Neera Nundy, Deval Sanghavi (individuals, Dasra co-founders) — edge: board, from dasra — named but not individually researched or channel-verified — high-value "mover over letterhead" candidates given Dasra's field-building role.  ← WRITTEN: neera-nundy — retired from LEADS 2026-09-11
- Skoll Foundation — edge: attends/co-funded (Skoll World Forum, SELCO/Dasra 2026 panel; also gave 2026 Skoll Award to Indus Action, India civic-tech) — global convener/funder, was being researched (channels found live) when the crawl was stopped — NOT yet written to a file. High priority to pick up first in the relaunch.  ← WRITTEN: skoll-foundation — retired from LEADS 2026-09-11
- Indus Action — edge: funded (2026 Skoll Award for Social Innovation winner) — India civic-tech/public-benefits-access nonprofit — not researched, notable enough to warrant its own file.  ← WRITTEN: indus-action — retired from LEADS 2026-09-11
- Antarang Foundation — see above (Skoll World Forum 2026 co-panelist with SELCO/Dasra) — not researched.  ← WRITTEN: antarang-foundation — retired from LEADS 2026-09-11
- responsAbility Investments — was mid-research (channels found live, India 2025/2026 investment list gathered: Sahyadri Farms, WheelsEMI, AMPIN, Ace International, Roserve Enviro, Qul Fruitwall) but the actor file was NOT yet written when the stop came — high priority to pick up first in the relaunch, most of the research is already done (see EDGES section above for the money detail).  ← WRITTEN: responsability-investments — retired from LEADS 2026-09-11
- IKEA Foundation — repeated here as the clearest single miss: cited three times (SELCO, Sustain Plus, GIZ) but never given its own record.  ← WRITTEN: ikea-foundation — retired from LEADS 2026-09-11

## PORTFOLIO / OPERATOR NAMES — seen, not detailed, wanted by new brief

- Ecozen Solutions (has a registry-depth file already — see WRITTEN)
- Vahan (gig-worker staffing platform, Villgro portfolio)
- Wysa (mental-health app, Villgro portfolio)
- Avni Wellness (Villgro's most recent investment, $170K seed, Oct 2025)
- iDreamCareer (Menterra + Gray Matters Capital co-investment, $1.63M seed)
- uFaber (Gray Matters Capital, ₹25cr Series A, online learning)
- ThinkZone (Gray Matters Capital portfolio, Cuttack/Odisha, low-cost education)
- Indian School Finance Company (Gray Matters Capital portfolio)
- Biofics Organics (Upaya Social Ventures, 2025 first-time investment)
- Bintix (Upaya Social Ventures, 2025 follow-on)
- Sahyadri Farms Post Harvest Care Limited (responsAbility, Jan 2025, premium fruit/veg platform)
- WheelsEMI (responsAbility, $10M, EV/two-wheeler financing)
- AMPIN Energy Transition (responsAbility, $35M, renewable C&I developer)
- Ace International Limited (responsAbility + FMO, Dec 2025, dairy/nutrition ingredients)
- Roserve Enviro (responsAbility, up to $25M, Mumbai wastewater treatment)
- Qul Fruitwall (responsAbility, Himalayan horticulture/cold storage)
- Punjab Renewable Energy Systems / PRESPL (Shell Foundation-funded; already has a related actor file, monish-ahuja.md, per pre-existing registry)

## DEAD ENDS

- Villgro Philippines — mentioned in a 2018 "replicate the Villgro model" reference on villgro.org but no live org page, LinkedIn or Twitter found; could not disambiguate from Villgro Africa's IIEF lineage. Not written.
- Invent (Villgro programme with GoI + DFID, launched 2016) — no independent org identity found; it appears to be a Villgro-internal programme name, not a separate actor. Not written as its own file; folded into villgro.md prose instead.
- Unconvention, iPitch — same as above: Villgro-internal programme/event brands, not separate actors. Folded into villgro.md prose.
- "Villgro" grep also hit no pre-existing dupes anywhere in problems/actors/ (165 files checked) — clean dedupe, no collision found for any of the 17 names written.
- Menterra's Twitter/X handle — searched but no confirmed live handle surfaced distinct from the LinkedIn company page; recorded LinkedIn only, did not invent a Twitter handle.
- Paul Basil's exact current title — sources conflict/are ambiguous: LinkedIn profile snippet references "Pollinate Impact" alongside Menterra; not reconciled or verified which is current — flagged in-file as unconfirmed rather than guessed.
- Lemelson Foundation, DOEN Foundation, Northern Arc Capital, Gray Matters Capital, Upaya Social Ventures — for all five, a LinkedIn company page was found but recency of posts could NOT be confirmed within the ~6-month window; each file records `status: unconfirmed` rather than inventing a "live" status. This is a systematic gap across the funder-type actors this wave — worth a dedicated channel pass in the relaunch.
- Shell Foundation's India-specific financial disclosure (annual India deployment figure) — not found; only programme-level detail (ClimaFii $45k grants) surfaced.
- Sankalp Forum's specific 2026 India edition dates — summit cadence/branding confirmed (Sankalp Global Summit, Sankalp Africa Summit, regional Bharat Summit) but exact 2026 India date not pinned down.
- Intellecap CEO Vikas Bali and Aavishkaar Group leadership (Vineet Rai, Vineet Chandra Rai) — named via Tracxn/company-profile scraping only; no primary-source bio page or channel fetched — treat these three names as unverified-depth until directly checked.

## STATE

- Waves completed: Wave 0 (Villgro) fully written. Wave 1 (8 actors: menterra, shell-foundation, srinivas-ramanujam, paul-basil, villgro-africa, ecozen-solutions, lemelson-foundation, doen-foundation) fully written. Wave 2 (selco-foundation, sankalp-forum, intellecap, aavishkaar-group, northern-arc-capital, gray-matters-capital, upaya-social-ventures) fully written — 7 of a planned ~8 (dasra was the 8th/first-of-wave-3 pick, see below).
- Wave 3 was just starting: dasra.md was written and complete. Skoll Foundation and responsAbility Investments had been researched (web searches done, channels checked, money figures gathered — see EDGES and the LEADS entries for both) but their actor files were NOT yet created when the stop instruction arrived. IKEA Foundation was researched only as a funder cited inline on selco-foundation.md, never given its own file.
- No file was left half-written or invalid. All 17 files on disk (villgro, srinivas-ramanujam, paul-basil, menterra, shell-foundation, villgro-africa, ecozen-solutions, lemelson-foundation, doen-foundation, selco-foundation, sankalp-forum, intellecap, aavishkaar-group, northern-arc-capital, gray-matters-capital, upaya-social-ventures, dasra) are complete records with full frontmatter and body sections.
- Next three moves, had the crawl continued: (1) write skoll-foundation.md and responsability-investments.md from the research already gathered above; (2) write ikea-foundation.md; (3) begin wave 4 from the individual-level leads (Vineet Rai, Wilfred Njagi, Neera Nundy/Deval Sanghavi) per the "mover over the letterhead" bias, plus Accion/BFA Global/Frontier Markets/Calvert Impact Capital/Triodos from the funder-edge leads.

---
# WAVE 2 ADDENDUM (2026-09-10 run)

## WRITTEN (13 new)

- skoll-foundation — funder/convener — registry — LinkedIn unconfirmed — global grantmaker, 2026 Skoll Award ($2M) to Indus Action
- responsability-investments — funder — tracked — LinkedIn live (2026 posts) — Zurich/Mumbai impact asset manager, 6 India deals Jan2025-Jan2026
- ikea-foundation — funder — registry — website only — global climate philanthropy, €404M 2025 payout, funds SELCO/Sustain Plus
- indus-action — operator — tracked — LinkedIn unconfirmed — 2026 Skoll Award winner, benefits-access civic tech, 2M reached vs 30M-by-2030 target
- antarang-foundation — operator/capacity-builder — registry — LinkedIn unconfirmed — adolescent skilling, 185K+ reached
- sahyadri-farms — operator — registry — website only — FPO grape/tomato exporter, ₹390cr raise Jan 2025
- vahan — operator — registry — LinkedIn unconfirmed — AI gig-recruitment, 500K+ placed, Villgro portfolio mention
- wysa — operator — registry — LinkedIn unconfirmed — AI mental-health chatbot, $29.5M raised, Villgro investor
- frontier-markets — operator — registry — LinkedIn unconfirmed — rural last-mile distribution, 20K Sahelis, DOEN-funded
- calvert-impact-capital — funder — registry — LinkedIn+X unconfirmed — US impact investor, $10M ECB to Northern Arc
- triodos-investment-management — funder — registry — LinkedIn unconfirmed — Dutch impact investor, EUR 5.4bn AUM, funds Ecozen
- accion — funder — registry — website only — global fintech-inclusion investor, funds Annapurna Finance/IKF Finance/Dvara KGFS
- vineet-rai — funder (individual) — registry — LinkedIn+X unconfirmed — Aavishkaar Group founder/VC, Intellecap co-founder/chairman

Operator ratio this wave: 5 of 13 (~38%) — slightly over the ⅓ cap; hold to ≤4 next wave.

## NEW EDGES

- skoll-foundation --funds--> indus-action
- skoll-foundation --convenes--> skoll-world-forum
- ikea-foundation --funds--> selco-foundation
- ikea-foundation --co-funded--> sustain-plus-energy-foundation
- responsability-investments --funds--> sahyadri-farms
- responsability-investments --funds--> wheelsemi / ampin-energy-transition / roserve-enviro / qul-fruitwall (all still unwritten operators)
- villgro --cohort--> vahan
- villgro --cohort--> wysa
- doen-foundation --funds--> frontier-markets
- northern-arc-capital --funded-by--> calvert-impact-capital
- ecozen-solutions --funded-by--> triodos-investment-management
- shell-foundation --co-funded--> accion (ClimaFii Alliance)
- accion --funds--> annapurna-finance, ikf-finance (named, unwritten)
- aavishkaar-group --board--> vineet-rai
- intellecap --board--> vineet-rai
- dasra/selco-foundation --attends--> antarang-foundation (Skoll World Forum 2026 panel)

## LEADS — carried forward + new

- Tarun Cherukuri (Indus Action founder-CEO) — individual file not written this pass (avoided dangling ref); in.linkedin.com/in/taruncherukuri — worth its own file next wave.  ← WRITTEN: tarun-cherukuri — retired from LEADS 2026-09-11
- Priya Agrawal (Antarang founder) — same reason, not written; worth its own file.  ← WRITTEN: priya-agrawal — retired from LEADS 2026-09-11
- Madhav Krishna (Vahan founder-CEO) — not written.  ← WRITTEN: madhav-krishna — retired from LEADS 2026-09-11
- Jo Aggarwal (Wysa co-founder-CEO) — not written.  ← WRITTEN: jo-aggarwal — retired from LEADS 2026-09-11
- Ajaita Shah (Frontier Markets founder-CEO, Schwab 2024 laureate) — not written; high "mover over letterhead" candidate, active WEF/Schwab circuit.
- BFA Global — still unresearched (ClimaFii Alliance co-funder, from shell-foundation) — carried from wave 1.  ← WRITTEN: bfa-global — retired from LEADS 2026-09-11
- Vikas Bali (Intellecap CEO) — still unverified/unresearched.  ← WRITTEN: vikas-bali — retired from LEADS 2026-09-11
- Wilfred Njagi (Villgro Africa CEO) — still not given own file.  ← WRITTEN: wilfred-njagi — retired from LEADS 2026-09-11
- Neera Nundy / Deval Sanghavi (Dasra co-founders) — still not researched individually.  ← WRITTEN: neera-nundy, deval-sanghavi — retired from LEADS 2026-09-11
- Annapurna Finance, IKF Finance, Dvara KGFS — Accion's named India investees, unresearched operators.  ← WRITTEN: annapurna-finance — retired from LEADS 2026-09-11
- WheelsEMI, AMPIN Energy Transition, Roserve Enviro, Qul Fruitwall, Ace International — responsAbility's remaining India portfolio (6 total, 1 sampled = Sahyadri Farms; 5 remain unresearched, per the operator sampling rule).  ← WRITTEN: wheelsemi, roserve-enviro — retired from LEADS 2026-09-11
- Sustain Plus Energy Foundation, GIZ India — IKEA Foundation's India partners, still unresearched.  ← WRITTEN: sustain-plus-energy-foundation, giz-india — retired from LEADS 2026-09-11
- Gray Matters Capital operators (uFaber, ThinkZone, Indian School Finance Company, iDreamCareer, Avni Wellness) — still unresearched, carried from wave 1.  ← WRITTEN: idreamcareer — retired from LEADS 2026-09-11
- Upaya Social Ventures operators (Biofics Organics, Bintix) — still unresearched, carried from wave 1.  ← WRITTEN: bintix — retired from LEADS 2026-09-11
- Villgro board members (Ashwin Mahalingam, Bharti Gupta Ramola, Dimple Gujral, Indumathi Nambi, Kairas Vakharia, Ranjeev Lodha, Sameer Mehta) — still unresearched, carried from wave 1.  ← WRITTEN: bharti-gupta-ramola, dimple-gujral, indumathi-nambi, kairas-vakharia, ranjeev-lodha, sameer-mehta — retired from LEADS 2026-09-11

## DEAD ENDS (new)

- None new this pass beyond wave 1's list — all 13 new actors resolved to a real, checkable source (website or LinkedIn) even where recency was unconfirmed.
- Systematic gap persists: nearly every funder-type record this wave landed on `status: unconfirmed` for its LinkedIn/X row — recency verification remains the weak point across the funder layer.

## STATE (end of this run)

- 194 actors total on disk (181 + 13 written this pass). `npm run validate`: 0 errors, 69 pre-existing warnings (none newly introduced). `npm run follow`: 121 to follow, 10 unreachable.
- Individual founder files (Tarun Cherukuri, Priya Agrawal, Madhav Krishna, Jo Aggarwal, Ajaita Shah) were deliberately deferred rather than written as stubs, to avoid either (a) a dangling `ref.actor` build error or (b) a thin individual record with no independently-verified channel. Next wave should research and write these five properly — they are the clearest "mover over the letterhead" candidates left un-actioned.
- Next wave's highest-value targets, in order: (1) the five founder individuals above, (2) BFA Global + remaining ClimaFii Alliance partners, (3) one more sampled operator each from responsAbility's and Gray Matters Capital's remaining portfolios (respecting the ≤4-per-parent / ≤⅓-of-wave cap), (4) Villgro's own board members for the cross-sector-bridge edges.

---
# INDIVIDUALS CONSOLIDATION PASS (2026-09-10)

## WRITTEN (9 new individuals)

- tarun-cherukuri — operator (individual) — registry — LinkedIn unconfirmed — Indus Action founder/CEO, 2026 Skoll Award
- ajaita-shah — operator (individual) — registry — LinkedIn (company post) unconfirmed — Frontier Markets founder, 2024 Schwab laureate
- madhav-krishna — operator (individual) — registry — LinkedIn unconfirmed — Vahan.ai founder/CEO
- jo-aggarwal — operator (individual) — registry — LinkedIn unconfirmed — Wysa co-founder/CEO
- priya-agrawal — operator (individual) — registry — LinkedIn unconfirmed — Antarang Foundation founder/director
- vikas-bali — intermediary (individual) — registry — X @intellecapceo unconfirmed — Intellecap CEO
- wilfred-njagi — intermediary (individual) — registry — LinkedIn unconfirmed — Villgro Africa co-founder/CEO
- neera-nundy — field-builder (individual) — registry — LinkedIn unconfirmed — Dasra co-founder/partner
- deval-sanghavi — field-builder (individual) — registry — LinkedIn unconfirmed — Dasra co-founder/partner, also founding board of Villgro (new edge)

## UPDATED

- vineet-rai.md — resolved the Vineet Rai / Vineet Chandra Rai question: same person, same LinkedIn URL (in.linkedin.com/in/vineet-rai-536160), cited elsewhere as "Chairman, Founder And CEO" (theorg.com). Added `aka: ["Vineet Chandra Rai"]`, widened role to "founder, chairman & CEO", added an in-body note explaining the resolution. No duplicate file created.

## NEW EDGES

- indus-action --board--> tarun-cherukuri (founder/CEO)
- frontier-markets --board--> ajaita-shah (founder)
- vahan --board--> madhav-krishna (founder/CEO)
- wysa --board--> jo-aggarwal (co-founder/CEO)
- antarang-foundation --board--> priya-agrawal (founder/director)
- intellecap --board--> vikas-bali (CEO)
- villgro-africa --board--> wilfred-njagi (co-founder/CEO)
- dasra --board--> neera-nundy (co-founder/partner)
- dasra --board--> deval-sanghavi (co-founder/partner)
- deval-sanghavi --board--> villgro (founding board member — newly surfaced, unresearched depth)

## NOTES

- All 9 records: `depth: registry`, `sources: [{status: unconfirmed}]` per brief — no fetches spent confirming recency, per budget.
- ajaita-shah and vikas-bali: no clean individual LinkedIn profile URL disambiguated from company/duplicate-name noise; recorded the best available source (company post / X handle) rather than inventing a personal URL.
- Deval Sanghavi's Villgro founding-board-member fact is a new cross-edge between Dasra and Villgro, both already tracked orgs — worth following up if a future wave touches Villgro's board again.
- validate: clean, 0 errors, 70 pre-existing warnings (all in other actors' `needs:` — none touched this pass). 203 actors total (194 + 9).
- follow-list: 203 actors, 130 to follow, 10 unreachable.

---
# WAVE 4 (2026-09-10 run — lead-backlog clearance)

## WRITTEN (15 new)

- wheelsemi — operator — registry — website unconfirmed — EV/2W lifecycle financing NBFC, responsAbility $10M debt
- roserve-enviro — operator — registry — website/LinkedIn unconfirmed — Mumbai industrial wastewater "pay-as-you-treat", responsAbility up to $25M
- idreamcareer — operator — registry — LinkedIn unconfirmed — career-counselling platform, Menterra+Gray Matters $1.63M co-invested seed (two-funder connectivity node)
- bintix — operator — registry — LinkedIn unconfirmed — Hyderabad waste-tech/recycling-data, Upaya's 6th waste investment
- annapurna-finance — operator — registry — LinkedIn unconfirmed — Odisha NBFC-MFI, Accion $35M raise (with Encourage Capital, Oikocredit)
- ashwin-mahalingam — capacity-builder (individual) — registry — LinkedIn unconfirmed — Villgro director, IIT Madras Civil Eng professor
- bharti-gupta-ramola — funder (individual) — registry — LinkedIn unconfirmed — Villgro director, ex-PwC partner, HDFC Life/SRF/Tata Steel boards
- dimple-gujral — capacity-builder (individual) — registry — none-found (no channel) — Villgro director, Tatha Partners, ex-Teach For India CFO
- indumathi-nambi — capacity-builder (individual) — registry — LinkedIn unconfirmed — Villgro director, IIT Madras Civil Eng professor
- kairas-vakharia — capacity-builder (individual) — registry — LinkedIn unconfirmed — Villgro director, Mahindra & Mahindra Farm Equipment Sector SVP
- ranjeev-lodha — capacity-builder (individual) — registry — LinkedIn unconfirmed — Villgro director, ex-Huhtamaki PPL CFO
- sameer-mehta — capacity-builder (individual) — registry — LinkedIn unconfirmed — Villgro director, Dr. Mehta's Hospitals Vice Chairman/Chairperson
- bfa-global — researcher/intermediary — registry — website live — inclusive-fintech research/advisory, ClimaFii Alliance co-funder
- sustain-plus-energy-foundation — intermediary/field-builder — registry — website live, LinkedIn unconfirmed — 150+-partner DRE platform, co-founded by SELCO/Social Alpha/CInI
- giz-india — funder/intermediary — registry — website live — German federal dev agency, IKEA Foundation smallholder-energy partner

Operator ratio: 5 of 15 (33%) — within cap.

## UPDATED

- villgro.md — added 7 new board ← edges (ashwin-mahalingam, bharti-gupta-ramola, dimple-gujral, indumathi-nambi, kairas-vakharia, ranjeev-lodha, sameer-mehta) + confirmed deval-sanghavi board edge
- deval-sanghavi.md — added `{actor: villgro, role: "founding board member"}` to affiliations frontmatter; confirmed via lidji.org + Wikipedia (was previously "unresearched depth")
- ikea-foundation.md — added `co-funded → giz-india` edge
- gray-matters-capital.md — added `funds → idreamcareer` edge
- upaya-social-ventures.md — added `funds → bintix` edge
- accion.md — added dated money figure to `funds → annapurna-finance` edge, marked ikf-finance as still-unwritten

## NEW EDGES

- responsability-investments --funds--> wheelsemi ($10M)
- responsability-investments --funds--> roserve-enviro (up to $25M, Jan 2026)
- gray-matters-capital --funds--> idreamcareer ($1.63M seed, co-invested with menterra)
- upaya-social-ventures --funds--> bintix (2025 follow-on)
- accion --funds--> annapurna-finance ($35M, Dec 2021, with Encourage Capital + Oikocredit)
- villgro --board--> ashwin-mahalingam / bharti-gupta-ramola / dimple-gujral / indumathi-nambi / kairas-vakharia / ranjeev-lodha / sameer-mehta
- deval-sanghavi --board--> villgro (confirmed, was unresearched)
- shell-foundation --co-funded--> bfa-global (ClimaFii Alliance; bfa-global.md now written)
- ikea-foundation --co-funded--> sustain-plus-energy-foundation (now written) / giz-india (now written)
- ashwin-mahalingam --board--> iit-madras-center-for-social-innovation-and-entrepreneurship (unresearched, new lead)
- kairas-vakharia --board--> iim-udaipur-incubation-centre / mitra (unresearched, new leads)
- bharti-gupta-ramola --board--> hdfc-life-insurance / srf-ltd / tata-steel / unitus-impact-fund / transforming-rural-india-foundation (unresearched, new leads)

## LEADS — carried forward + new

- AMPIN Energy Transition, Qul Fruitwall, Ace International — responsAbility's remaining unsampled India deals (2 of 6 now written: Sahyadri Farms, WheelsEMI, Roserve Enviro = 3 of 6; 3 remain).
- uFaber, ThinkZone, Indian School Finance Company, Avni Wellness — Gray Matters Capital's remaining unsampled operators (1 of 5 now written: iDreamCareer).
- Biofics Organics — Upaya's other 2025 investment, still unwritten (Bintix now written).
- IKF Finance, Dvara KGFS — Accion's remaining named India investees (Annapurna Finance now written).
- IIT Madras Center for Social Innovation and Entrepreneurship — Ashwin Mahalingam's other board seat; a second India academic-incubator, unresearched.
- Okapi Research and Advisory — Ashwin Mahalingam's co-founded firm, unresearched.
- Carbon Zero Challenge — Indumathi Nambi's national cleantech student contest, a convener edge, unresearched.
- IIM Udaipur Incubation Centre, M.I.T.R.A. — Kairas Vakharia's other board seats, unresearched.
- HDFC Life Insurance, SRF Ltd, Tata Steel Ltd, Unitus Impact Fund (GP advisory board), Transforming Rural India Foundation (advisory council) — Bharti Gupta Ramola's other seats; Unitus Impact Fund especially high-value (an impact-fund GP board), unresearched.  ← WRITTEN: unitus-impact-fund, transforming-rural-india-foundation — retired from LEADS 2026-09-11
- Tatha Partners, Dalberg Global Development Advisors, India School Leadership Institute — Dimple Gujral's other affiliations, unresearched.
- Huhtamaki PPL, IVP Ltd — Ranjeev Lodha's other board seats, unresearched.
- Dr. Mehta's Hospitals, India Home Health Care, Atlas Advisory, Everonn Medical Education — Sameer Mehta's other affiliations, unresearched.
- Punjab Renewable Energy Systems / PRESPL portfolio-adjacent leads (Neev Fund, SIDBI) — cited in monish-ahuja.md, not yet cross-checked against this network.  ← WRITTEN: punjab-renewable-energy-systems — retired from LEADS 2026-09-11
- Encourage Capital, Oikocredit — Annapurna Finance's other co-investors (Dec 2021 raise), unresearched.
- Faering Capital, Elevar Equity, Women's World Banking — WheelsEMI's other investors, unresearched.
- Concord Enviro Systems, Danish Climate Investment Fund (DCIF) — Roserve Enviro's JV parents, unresearched.
- Ayush Bansal, Pravesh Dudani (iDreamCareer founders) — individual "mover over letterhead" candidates, not written this pass (avoided dangling-ref risk; org-level record only).  ← WRITTEN: ayush-bansal, pravesh-dudani — retired from LEADS 2026-09-11
- Roshan Miranda, Udit Patidar, Jayanarayan Kulathingal (Bintix founders) — same reason, not written.  ← WRITTEN: roshan-miranda — retired from LEADS 2026-09-11
- Gobinda Chandra Pattnaik (Annapurna Finance MD/founder) — same reason, not written; high-value MFI-sector individual.  ← WRITTEN: gobinda-chandra-pattnaik — retired from LEADS 2026-09-11
- Srinivas Kantheti et al. (WheelsEMI founders) — same reason, not written.
- Prerak Goel, Prayas Goel (Roserve Enviro founders) — same reason, not written.  ← WRITTEN: prerak-goel, prayas-goel — retired from LEADS 2026-09-11

## DEAD ENDS (new)

- Dimple Gujral — no personal LinkedIn URL could be disambiguated from several same-name/wrong-person profiles (Securian Financial Group employees, etc.); recorded `status: none-found` rather than guessing.
- Menterra CEO/Villgro CEO channel searches not repeated this pass (already resolved prior waves).
- Ranjeev Lodha — two same-name LinkedIn profiles found (ranjeev-lodha-61b6716 vs ranjeev-jolly-lodha-61672821); only the one matching the Huhtamaki/Tata Chemicals/M&M career path was recorded.
- Vikas Bali's X handle (@intellecapceo, recorded prior pass) not re-verified this pass — no fetch spent.
- No PDFs, annual reports or filings fetched this pass; 0 page fetches, all research from search snippets (holding the line from waves 2-3).

## STATE (end of this run)

- 218 actors total on disk (203 + 15 written this pass). `npm run validate`: 0 errors, 70 warnings (identical count to pre-pass baseline — none newly introduced). `npm run follow`: 144 to follow, 11 unreachable.
- Next wave's highest-value targets, in order: (1) the ~10 named-founder individuals deferred this pass (Ayush Bansal, Gobinda Chandra Pattnaik, Srinivas Kantheti, Roshan Miranda, Prerak/Prayas Goel) per "mover over letterhead"; (2) the second board/advisory seats surfaced by this pass's 7 Villgro directors (Unitus Impact Fund GP board and IIT Madras CSIE are the two highest-signal); (3) remaining responsAbility (AMPIN, Qul Fruitwall, Ace International) and Gray Matters (uFaber, ThinkZone, ISFC, Avni Wellness) portfolio samples, respecting the ≤4/parent and ≤⅓-of-wave caps; (4) IKF Finance / Dvara KGFS (Accion) and Biofics Organics (Upaya) to close out the named-investee leads cleanly.

---
# OPERATOR-FOUNDERS + BHARTI-GUPTA-RAMOLA CONSOLIDATION PASS (2026-09-10)

## WRITTEN (9 new)

- ayush-bansal — operator (individual) — registry — LinkedIn unconfirmed — iDreamCareer co-founder/CEO
- pravesh-dudani — operator (individual) — registry — LinkedIn unconfirmed — iDreamCareer co-founder (exited), now Medhavi Skills University
- roshan-miranda — operator (individual) — registry — LinkedIn unconfirmed — Bintix founder/director, ex-Waste Ventures India
- gobinda-chandra-pattnaik — operator (individual) — registry — none-found — Annapurna Finance founder/CMD/CEO, no personal channel disambiguated
- srinivas-kantheti — operator (individual) — registry — LinkedIn unconfirmed — WheelsEMI co-founder/MD, ex-Bajaj Auto
- prerak-goel — operator (individual) — registry — LinkedIn unconfirmed — Roserve Enviro co-founder (profile match not fully confirmed)
- prayas-goel — operator (individual) — registry — none-found — Roserve Enviro co-founder, no channel found
- unitus-impact-fund — funder — registry (user-flagged for promotion on ask) — LinkedIn+X unconfirmed — aka Patamar Capital, GP advisory seat held by Bharti Gupta Ramola
- transforming-rural-india-foundation — field-builder/capacity-builder — registry — X+LinkedIn unconfirmed — TRIF, Bharti Gupta Ramola's advisory-council seat

## UPDATED

- bharti-gupta-ramola.md — added board edges to unitus-impact-fund and transforming-rural-india-foundation (now written); pruned HDFC Life/SRF/Tata Steel edges to prose-only per the new prune-by-relevance rule.

## NEW EDGES

- idreamcareer --board--> ayush-bansal (co-founder & CEO)
- idreamcareer --board--> pravesh-dudani (co-founder, exited 2023)
- bintix --board--> roshan-miranda (founder & director)
- annapurna-finance --board--> gobinda-chandra-pattnaik (founder, CMD & CEO)
- wheelsemi --board--> srinivas-kantheti (co-founder & MD)
- roserve-enviro --board--> prerak-goel / prayas-goel (co-founders)
- bharti-gupta-ramola --board--> unitus-impact-fund (GP advisory board)
- bharti-gupta-ramola --board--> transforming-rural-india-foundation (advisory council)
- transforming-rural-india-foundation --board(lead, unwritten)--> Harish Hande (SELCO Foundation founder, no individual file yet)

## PRUNED (new rule — logged, not crawled)

- Bharti Gupta Ramola --board--> HDFC Life Insurance — pruned; listed-company board seat, out of segment scope. Recorded as prose in bharti-gupta-ramola.md only.
- Bharti Gupta Ramola --board--> SRF Ltd — pruned; same reason.
- Bharti Gupta Ramola --board--> Tata Steel Ltd — pruned; same reason (the exact edge the user flagged as the trigger for this rule).

## LEADS — unresearched, next-wave seed set

- Medhavi Skills University / Medhavi Foundation (Pravesh Dudani's current venture) — unresearched, adjacent skilling-sector lead.
- Waste Ventures India (Roshan Miranda's prior venture) — unresearched.
- Harish Hande — named as a Transforming Rural India Foundation board member per search snippet; already the founder-figure behind selco-foundation.md but has no individual actor file of his own — high-value "mover over letterhead" candidate for a future wave.  ← WRITTEN: harish-hande — retired from LEADS 2026-09-11
- Rashmi Shukla Sharma (TRIF board chair), Anish Kumar (TRIF Managing Director), Dr Sanjiv Phansalkar, Ashish Deshpande, Roda Mehta — TRIF's other named leadership, unresearched.
- India Rural Colloquy — TRIF's annual convening; speaker list unresearched, worth a wave.
- Unitus Ventures (formerly Unitus Seed Fund) and Unitus Capital — two DISTINCT entities from Unitus Impact Fund/Patamar Capital, sharing only the "Unitus" name/lineage; surfaced during disambiguation, not researched or written — flag to avoid future conflation.
- Concord Enviro Systems, Danish Climate Investment Fund (DCIF) — Roserve Enviro's JV parents, still unwritten (carried from wave 4).

## DEAD ENDS (new)

- Gobinda Chandra Pattnaik — no personal LinkedIn/X profile found distinct from the company page; recorded `status: none-found`.
- Prayas Goel — no personal channel found; only a third-party net-worth aggregator page surfaced, not treated as a live source.
- Prerak Goel — multiple same-name LinkedIn profiles (including one tagged "Myntra"); recorded the Concord/Roserve-matching profile as best-match, unconfirmed disambiguation.
- 0 page fetches this pass — all research from search snippets, per budget instruction.

## STATE (end of this run)

- 227 actors total on disk (218 + 9 written this pass). `npm run validate`: 0 errors, 70 warnings (identical baseline, none newly introduced). `npm run follow`: 151 to follow, 13 unreachable.
- Two validation errors surfaced and fixed mid-pass: `prerak-goel.md` / `prayas-goel.md` had `affiliations.0.from: ""` (empty string, not a valid YYYY/YYYY-MM/YYYY-MM-DD) — removed the empty `from` key entirely rather than inventing a date.
- Crawl deliberately did not fan out beyond the two named orgs' immediate board seats — Villgro's other directors' further seats (IIT Madras CSIE, IIM Udaipur Incubation Centre, Huhtamaki PPL, etc., carried from wave 4) remain untouched leads.

---
# HARISH HANDE CONSOLIDATION (2026-09-10, single-actor, no fan-out)

## WRITTEN (1)

- harish-hande — field-builder/capacity-builder (individual) — registry — LinkedIn unconfirmed — SELCO India co-founder (1995), SELCO Foundation founder & CEO (2010), Ramon Magsaysay laureate (2011), TRIF board member

## UPDATED

- selco-foundation.md — added `board → harish-hande (founder & CEO)` edge to Scope
- transforming-rural-india-foundation.md — replaced the unwritten-lead line with `board ← harish-hande (board member)`

## NOTES

- No SELCO India actor record exists and none was created per instruction — logged as a lead only (co-founder edge, prose in harish-hande.md).
- No stated, dated, individually-quotable ask found — SAFDE 2025 "call for investment and policy support" is a collective sector statement, not personally attributable — depth stayed `registry`.
- LinkedIn profile found (harish-hande-67b226, multiple posts) but no post independently dated within ~6 months this pass — recorded `status: unconfirmed`, not `live`. No X/Twitter handle found.
- Caught mid-pass: first draft omitted mandatory `ecosystem_role:` — validate warned "attaches to nothing"; fixed to `[field-builder, capacity-builder]`.
- No commercial/academic board seats surfaced for Hande beyond the two org affiliations already tracked — nothing to prune this pass.
- Budget: 2 web searches (LinkedIn/X handle; ask-hunting), 0 page fetches. One record written, two records edited.
- 228 actors total on disk. `npm run validate`: 0 errors, 70 warnings (baseline restored). `npm run follow`: 152 to follow, 13 unreachable.

---
# IMPACT ACCELERATORS SEGMENT CRAWL (2026-09-11, seed: "impact accelerators", waves: 2)

## WRITTEN (14 new)

- social-alpha — capacity-builder/funder/intermediary — tracked — LinkedIn+founder LinkedIn live (2026 posts) — deep-science/climate/health venture-development platform, 300+ innovations, $350M+ unlocked since 2016
- manoj-kumar — capacity-builder/funder (individual) — registry — LinkedIn live (2026 posts) — Social Alpha founder/CEO, ex-Villgro co-founder (spun-out-of edge)
- unltd-india — capacity-builder/funder — registry — LinkedIn unconfirmed — Mumbai social-entrepreneur incubator since 2007, ~4-company active portfolio
- padcare-labs — operator — registry — LinkedIn(founder) unconfirmed — UnLtd India portfolio, menstrual-waste recycling hardware, $3.62M raised
- recircle — operator — registry — LinkedIn unconfirmed — UnLtd India + Upaya Social Ventures portfolio, dry-waste/Safai Saathi network, 310 cities
- rechargion-energy — operator — registry — website live — Social Alpha Techtonic cohort, sodium-ion battery manufacturer
- ciie-co — capacity-builder/funder/intermediary — tracked — LinkedIn unconfirmed — IIM Ahmedabad incubator (aka IIMA Ventures), Bharat Inclusion Initiative ($25M target seed fund)
- kunal-upadhyay — capacity-builder/intermediary (individual) — registry — LinkedIn unconfirmed — CIIE.CO co-founder/CEO
- ashoka-india — field-builder/convener/capacity-builder — registry — LinkedIn unconfirmed — India chapter of global Ashoka Fellowship, 350+ Fellows
- shruti-nair — field-builder/convener (individual) — registry — LinkedIn unconfirmed — Ashoka South Asia leader
- gates-foundation — funder — registry — LinkedIn+X unconfirmed — $2.47M grant to Social Alpha (Nov 2022), co-funds Bharat Inclusion Initiative
- michael-susan-dell-foundation — funder — registry — LinkedIn unconfirmed — co-funds Bharat Inclusion Initiative, New Delhi office
- tata-trusts — funder/field-builder — registry — LinkedIn+X unconfirmed — seeds both CIIE.CO's Bharat Inclusion Initiative and India Health Fund
- india-health-fund — funder/intermediary — registry — LinkedIn unconfirmed — Tata Trusts-seeded infectious-disease innovation fund, co-run with Social Alpha, targeting $150M/5yr

Operator ratio: 3 of 14 (21%) — within cap.

## NEW EDGES

- social-alpha --funded-by--> gates-foundation ($2.47M, Nov 2022)
- social-alpha --funded-by--> tata-trusts (via India Health Fund)
- social-alpha --co-funded--> india-health-fund
- social-alpha --cohort--> rechargion-energy (Techtonic clean-energy cohort)
- social-alpha --board--> manoj-kumar (founder & CEO)
- manoj-kumar --spun-out-of--> villgro (early co-founder, moved on to found Social Alpha) [NEW cross-edge: Social Alpha and Villgro networks now connect]
- unltd-india --incubatee--> padcare-labs
- unltd-india --incubatee--> recircle
- recircle --funded-by--> upaya-social-ventures [NEW cross-edge: UnLtd India network connects to the existing Villgro/Upaya cluster]
- ciie-co --funded-by--> gates-foundation (Bharat Inclusion Initiative)
- ciie-co --funded-by--> michael-susan-dell-foundation (same)
- ciie-co --funded-by--> tata-trusts (seed support)
- ciie-co --board--> kunal-upadhyay (co-founder & CEO)
- ashoka-india --board--> shruti-nair (South Asia leader)
- tata-trusts --funds--> india-health-fund (seeding trust, 2017)
- tata-trusts --funds--> ciie-co (Bharat Inclusion seed support)

## PRUNED

- Omidyar Network — edge: funded-by, from ciie-co (Bharat Inclusion Initiative, one of three founding funders) — pruned from a full record; India operations wound down completely by end of 2024 (announced Dec 2023), so it no longer funds into the segment. Noted in ciie-co.md prose as a former funder instead. Global Omidyar Network remains active elsewhere but has zero current India relevance, failing the "would this actor plausibly appear in this map on its own merits, now" test.
- Vipul Patel (CIIE.CO Partner, Seed Investing) — edge: board, from ciie-co — named in ciie-co.md prose/Scope as a lead but not given his own file this pass; no independently verified personal channel surfaced in the search budget spent, and a second individual record for the same org was lower priority than closing out the funder layer.
- Pooja Warier Hamilton (UnLtd India co-founder) — edge: board, from unltd-india — named in prose but not researched to record depth; she may no longer be active at the org (current CEO succession itself is unresolved — see DEAD ENDS).
- Ajinkya Dhariya, Rahul Nainani, Gurashish Singh Sahni, Vilas Shelke — operator-company founders (PadCare Labs, ReCircle, Rechargion Energy) — named in their org records' prose/sources but not given individual files, per the operator-sampling budget; the org record is the unit this pass, individuals are a future-wave lead.

## LEADS — next wave, unresearched

- Trestle Labs — edge: incubatee, from unltd-india — assistive-tech-for-the-visually-impaired company, named as UnLtd India's third notable portfolio company, not sampled (portfolio capped at 2 for this org this pass).
- PadUp Ventures, GivFunds — edge: co-funded, from unltd-india — named partners for co-financed programmes and low-cost lending access; not researched.
- Vipul Patel (CIIE.CO Partner, Seed Investing) — see PRUNED above; worth a channel-verification pass on its own, low cost.
- Ashoka India Fellows (350+) — edge: cohort, from ashoka-india — a large one-to-many portfolio, explicitly not enumerated; worth sampling 2-4 named Indian Fellows (especially any working climate/livelihoods, to cross-connect with the existing tier-1 leaf network) in a future wave.
- Suneeta Krishnan (Gates Foundation India, Deputy Director Strategy) — edge: board, from gates-foundation — named in a bio snippet, not individually verified or written.
- Aditya Jagati (Gates Foundation, LinkedIn hit) — edge: board, from gates-foundation — same caveat, not researched.
- Michael & Susan Dell Foundation India named programme leads — not surfaced this pass; only the org-level LinkedIn/website found.
- 3one4 Capital, Brigade Group, PKRBCV Shroff Trust, JioGenNext, Marico Innovation Foundation — edge: funded-by, from padcare-labs (5 of 29 total investors named) — mainstream/CSR-adjacent investors, India-relevance/segment-fit unchecked; JioGenNext and Marico Innovation Foundation look the most segment-relevant if picked up.
- Venture Catalysts, Mumbai Angels, Flipkart — edge: funded-by, from recircle — same caveat; mainstream investors, low segment fit likely, check before writing.
- ARAI-AMTIF (Ministry of Heavy Industries), UNIDO, US-India Science & Technology Endowment Fund — edge: funded-by, from rechargion-energy — institutional/multilateral funders of deep-tech manufacturing, not researched; UNIDO is the most likely to recur across other India climate-hardware actors.
- Pooja Warier Hamilton, Dr Akhil Shahani, Maya Shahani (SAGE Foundation) — UnLtd India's founding/governance lineage — not researched to record depth; current CEO succession (Anshu Bhartia → ?) unresolved, worth resolving before treating unltd-india.md's leadership line as current.
- Global Fund (to Fight AIDS, TB and Malaria) — edge: co-funded, from india-health-fund — major multilateral, India-relevant strategic partner, not researched.

## DEAD ENDS

- Anshu Bhartia's current role at UnLtd India — search results conflict: one source names her CEO as of Dec 2022, another (Crunchbase/ZoomInfo) shows her as CEO of Exper Executive Education with no current UnLtd India title. Could not resolve within budget; recorded unltd-india.md's leadership line as unconfirmed rather than naming a possibly-stale CEO, and did not write Bhartia her own individual file for the same reason.
- Omidyar Network — see PRUNED; confirmed via multiple 2023/2024 press reports (TechCrunch, Entrackr, Inc42, ImpactAlpha) that India operations wound down by end of 2024; not written as a full record.
- Gates Foundation India's specific 2026 LinkedIn post date — a snippet referenced "AI for Social Good and Inclusion" but the exact date was not independently opened/confirmed; recorded `status: unconfirmed` rather than `live`.
- 1 page fetch spent this pass (gatesfoundation.org grant-disclosure page, for the one money figure used); all other research from search snippets, holding the token-discipline line.

## STATE (end of this run)

- 242 actors total on disk (228 + 14 written this pass). `npm run validate`: 0 errors, 70 warnings (identical baseline, none newly introduced — one mid-pass fix: manoj-kumar.md was drafted `depth: tracked` with `needs: []`, corrected to `registry` before commit). `npm run follow`: 165 to follow, 13 unreachable.
- Segment take: "impact accelerators" as a seed fanned out cleanly into two clusters — (1) Social Alpha, which shares a founder lineage with Villgro (manoj-kumar --spun-out-of--> villgro) and now shares a funder layer (Gates Foundation, Tata Trusts) with the existing network; (2) CIIE.CO/Bharat Inclusion Initiative, funded by the same Gates Foundation + Tata Trusts pairing plus Michael & Susan Dell Foundation, with Omidyar Network pruned as a lapsed funder. UnLtd India and Ashoka India are smaller, standalone nodes with their own portfolio/cohort fans not yet sampled beyond 2-3 names each.
- Next wave's highest-value targets, in order: (1) resolve UnLtd India's current CEO/leadership before any outreach; (2) sample 2-4 Ashoka India Fellows for the cohort edge; (3) Vipul Patel channel check (cheap, one search); (4) Global Fund and UNIDO as recurring multilateral-funder nodes likely to reappear across other India deep-tech/health actors.

# IMPACT ACCELERATORS CLOSE-OUT PASS (2026-09-11, continuation of the above)

## VERIFIED / NO NEW FILES NEEDED (P1)

- responsability-investments.md, skoll-foundation.md, ikea-foundation.md — all three already exist on disk (written 2026-09-10, in an earlier section of this file, contrary to the "never written" framing in the LEADS block above). Verified content is complete (needs/offers/sources/Scope all present). No action needed.

## CHANGED

- michael-susan-dell-foundation.md (P5) — resolved: found a second, independent India edge (`funds → menterra`, one of 5 LPs in Menterra Social Impact Fund I, ₹40cr 2016 — via PitchBook/Inc42), so the record no longer rests on the single ciie-co edge. Added prose on its historical $50M direct-investing earmark and 25+ portfolio companies (Inc42/PhilanthropyNewsDigest). Left `depth: registry`, `needs: []` — no stated ask found.
- menterra.md — added reciprocal `funded-by → michael-susan-dell-foundation` edge.
- gates-foundation.md (P4) — X (@BMGFIndia) upgraded `unconfirmed → live`, confirmed post 19 Feb 2026 (India AI Impact Summit). LinkedIn left `unconfirmed` — two 2026-dated post URLs found in snippets but neither independently opened.
- tata-trusts.md, india-health-fund.md (P4) — re-checked; no post confirmable within ~6 months (Tata Trusts snippets dated to 2023-24; India Health Fund's only dated post ties to Nov 2024's Women Entrepreneurs Day). Both `status: unconfirmed` retained, reasoning logged in each file.
- social-alpha.md (P2) — added `portfolio → ~300, 1 sampled` Scope line; noted count variance across sources (261-300+).
- ciie-co.md (P2) — added `portfolio →` Scope line; count disagrees sharply by source (79 to 439 investments) — written as a range, not picked silently; 0 sampled.
- unltd-india.md (P3 — RESOLVED) — Anshu Bhartia's own LinkedIn confirms she has left UnLtd India; current title is CEO of Exper Executive Education (unrelated org), UnLtd India listed as a past role. The contradiction is resolved (she is not current CEO); no successor name found, so that gap is now stated as an open unknown rather than an unresolved conflict.

## NOT REACHED — P6, P7

Budget stopped after P5. Trestle Labs, PadUp Ventures, GivFunds (P6 UnLtd India edges), Ashoka India Fellow sampling (P6), and Global Fund / UNIDO (P7) were not researched this pass — still open leads, same as the prior LEADS block above.

## STATE (end of this run)

- 242 actors total on disk (no new files written this pass — all five targeted actions were edits to existing records). `npm run validate`: 0 errors, 70 warnings (identical baseline). `npm run follow`: 165 to follow, 13 unreachable.
- Next wave's highest-value targets, in order: (1) Trestle Labs (UnLtd India's 3rd portfolio sample, room under the ≤4 cap); (2) 2-4 named Ashoka India Fellows sampled by need-legibility; (3) Global Fund and UNIDO as recurring multilateral nodes; (4) a named successor CEO at UnLtd India, if one surfaces.
