# The feed that used to work

I have been losing interest in Reddit.

Not dramatically. There was no incident. Over some months the proportion of things worth reading fell, the proportion of things designed to make me angry rose, and I began opening the app less. When I noticed I was doing it, I tried to work out what had actually changed — because the version of Reddit I joined worked well, and I could describe precisely how it worked.

It worked like this: I subscribed to maybe forty communities. Most posts I scrolled past. Every so often something stopped me, and I read the comments, and occasionally I learned something. My engagement rate was low. That was fine. The low rate was not a defect of the feed — it was the room in which the interesting thing could show up.

What replaced it was a feed increasingly composed of things I never subscribed to, selected because they provoke a response. And the first theory I had about why is, I now think, mostly wrong. It is worth writing down anyway, because the way it failed is the actual argument.

## The first theory

The theory was: an information channel gets captured. Someone starts pushing sensational and polarising content. It generates engagement. Engagement is what the channel optimises, so it promotes more of it. That drives away the people who came for something else, but net engagement keeps rising, so the channel reads the whole process as success and keeps going.

I had examples ready. Older people arriving on Facebook while younger users left for Instagram. Twitter permitting more polarising content while Threads picked up the exits. Television news losing an entire generation. And a revenue story layered on top: traditional media choosing polarising content because of who its advertisers were, social media making ads themselves a friction.

Three parts of that are wrong.

**Advertisers do not push toward polarisation — they push away from it.** Brand safety and boycotts pull platforms toward the bland middle. X's polarisation is what *cost* it advertisers, and pushed it toward subscriptions. Fox News made most of its money from carriage fees rather than advertising, which is to say it was subscription-like, and that is *why* it could polarise. The real exception is when the advertiser is itself a political actor — state advertising allocations to Indian print and television are genuine advertiser capture, and that is a different mechanism from the one I was describing.

**Comment volume does not fall as a channel degrades. It rises.** Polarising content is response-evoking by construction. I had assumed the decay signal would be visible as declining discussion; it is the opposite, and that inversion turns out to matter more than the original point.

**And the process is not irreversible.** I had written "irreversible decay" without a mechanism, which is the kind of phrase that feels strong and asserts nothing. What I could actually defend was churn.

What survived the corrections was smaller and better.

## The part that is real, and measured

The core claim — polarising content drives engagement up and drives some users out simultaneously — is not speculation. The operator's own research says so.

Facebook's 2018 News Feed change, internally called MSI (meaningful social interactions), upweighted comments, shares and reactions. A 2019 internal memo from Facebook's own data scientists found "strong evidence" of "unhealthy side effects on important slices of public content, such as politics and news." Facebook's research found that angry content receives more engagement and that political actors exploited this. This is not an outside critic's inference. It is the company's own finding, in its own documents.

The composition shift has been measured too, and more sharply than I had it. A field experiment published in *Science Advances* found that perceiving a discussion as toxic predicted **both** lurking **and** power-usership. The same perception drives some people silent and others louder.

That is the whole problem in one sentence. Engagement is users multiplied by intensity. One input produces two opposite behavioural responses, and the aggregate metric cannot tell them apart. A channel watching engagement rise cannot distinguish a growing audience from a shrinking, hotter one.

The literature calls the outcome a spiral of toxicity: hostile users produce more, moderates go quiet, and what remains is a smaller and more radical community. My version had the same shape, but I had been treating the departures as the primary event. The measurement failure is the primary event. The departures are just what it costs.

## Why the damage arrives all at once

The other thing I got wrong was assuming the aggregate metric always masks the decay. Sometimes it does not.

At X, usage and advertising revenue fell visibly and fast. Pew found usage among 18-to-29-year-olds — the most valuable demographic — dropping from 42% to 33% in a single year between 2024 and 2025. eMarketer projected around seven million US monthly active users lost between 2022 and 2025. Bluesky went from five million users in February 2024 to thirty-five million by January 2025. None of that was hidden.

At Facebook during the MSI years, it was completely hidden. So the mask is not a property of the mechanism. It is a phase of it, and what sustains the phase is *inflow*. Facebook had an incoming cohort — older users arriving — large enough to cover the young cohort's exit. The moment inflow stops covering outflow, the same churn that was invisible becomes the headline.

Which means the correct model has two stages. Stage one: masked churn, where departures are real and the top-line number grows anyway, and the channel accelerates the thing killing it because it reads the number as validation. Stage two: visible churn, where inflow stops and the accumulated damage surfaces at once.

This also explains why decay always looks sudden from outside. Dissatisfaction accumulates silently while switching costs hold. Nobody leaves a channel that has no substitute — they just quietly hate it. Bluesky's existence is what converted years of stored dissatisfaction at X into measurable departure. The discontent long predated the exit.

So churn is not proportional to harm. It is proportional to harm multiplied by the availability of an exit. A platform can accumulate enormous unregistered damage while every metric it owns looks healthy, and then discharge all of it in one quarter when someone builds an alternative.

## Polarisation is not the mechanism

The more I pushed on this, the less polarisation looked like the cause of anything.

Every channel has a **fixed surface**: a finite amount of a person's attention, a finite number of slots. Everything served competes for the same slots. Polarising content is one claimant on that surface. There are at least three others.

**Volume.** Newcomers arriving faster than a community can transmit its norms — the Usenet problem, still unsolved thirty years later. **Audience merger.** Your parents show up, so you cannot perform the same self, and you post less — what researchers call context collapse. **Paid placement.** Ads and sponsored slots taken directly out of the relevance surface.

All four produce the same measurable outcome: the share of surface occupied by things the user did not want goes up. Which means they are *substitutable*. A platform that fixes its polarisation problem while raising ad load has done nothing. This is the reason content moderation, on its own, is not a defence — it addresses one claimant on a surface with four.

It also forced me to give up my best-known example. Facebook to Instagram was not a polarisation story. The young cohort left because the older cohort arrived — their content filled the feed, *and* their presence made posting uncomfortable. One influx, two harms, both consequences of unregulated inflow rather than of angry content. Facebook's politicisation largely came afterwards. My flagship example was evidence for a different mechanism than the one I was using it to support.

Reddit is the cleaner case, and it is structurally immune to the Facebook failure — pseudonymous, per-community identity, no persistent social graph watching you. What happened there was volume and capture, and it was not accidental. In roughly eighteen months Reddit priced third-party apps out of existence (which also destroyed a large part of the unpaid moderation layer), licensed its content into Google search (importing drive-by visitors with no community context), went public (installing an ownership structure that cannot absorb a composition fix), and expanded algorithmic injection of non-subscribed content into the home feed.

Every one of those routes content *around* the community boundary. Reddit's defence against capture was its topology — the sub was the unit that did the moderating — and it dismantled that defence four different ways.

## The failure with no villain

Then there is a failure mode that has nothing to do with polarisation at all, and I think it is the most interesting one.

Too many posts about something I care about deeply is also overwhelming. Not polarising. Not irrelevant. Extremely relevant, and precisely because it is relevant, it saturates. A disaster, a war, an event I genuinely want to follow — served at 20% of my feed for three weeks, it stops being information and becomes load.

This is measured, at population scale. The Reuters Institute's Digital News Report 2025 finds 40% of people worldwide now avoid news at least sometimes, up from 29% in 2017. The reasons are reported separately: negative effect on mood 39%, **feeling overwhelmed 31%**, too much conflict coverage 30%, powerlessness 20%. Overwhelm and conflict are distinct, near-equal causes. Saturation is not a smaller problem than polarisation. It is the same size, and almost nobody is building against it.

TikTok is the exception. In December 2021 it announced it was interrupting content *clusters* rather than individual items — content about sadness, breakups, extreme dieting, loneliness, that is "fine as a single video but problematic if viewed in clusters" — developed with the International Association for Suicide Prevention and Boston Children's Hospital's Digital Wellness Lab, alongside a tool letting users declare topics to avoid. Their feed also generally won't show two consecutive videos from the same creator or using the same sound.

The important part is that saturation is invisible to every metric that would catch the other failures. A feed can have perfectly healthy topic diversity measured over a day and still deliver a fifth of its slots to the same heavy subject for a month. And engagement with that content is *high*, which means an engagement optimiser reads a saturated user as a delighted one.

## What you would actually measure

Here is where the two failure classes separate, and where I think most platforms go wrong.

There are dials a platform sets directly — ad load, inflow rate, the share of feed given to non-subscribed injection. These insert content orthogonal to what the user wants. The share of served items that get engaged with **falls**. That metric already exists everywhere; e-commerce teams compute a version of it as "percentage of revenue attributable to recommendations," though they use it to allocate credit to the recommendations team rather than as a health signal.

Then there are failures the platform only reaches through incentives — capture, saturation. Here the surface gets *narrower and more engaging*. The same metric **rises**.

Two failure classes, one metric, opposite signs. A platform with a perfectly good relevance metric will read a capture failure through it and conclude everything is fine. That is not a missing-instrument problem. It is a wrong-instrument problem, and it is worse, because the instrument returns a confident answer.

So the metric cannot be about hit rate, and it cannot be about content. What I want is a description of **whether the surface is still doing its job**, which I would define as: on average some proportion of what is served lands, that engagement is distributed across topics, and it is distributed across depth.

Depth matters as much as breadth, and it is the part that gets ignored. Engagement is not binary. There is a ladder — an item ignored, tapped, read through, saved, acted on, returned to — and a healthy surface produces a spread across it. A surface where everything gets a shallow tap is habituated scrolling. A surface where everything gets a deep response is either saturation or capture. The distribution across the ladder is a proxy for emotional load that requires no model of emotion at all, which is the only reason it is practical.

## What Reddit's subscribed feed was actually doing

This also clarified what I lost.

Subscribing to a community is a request — but a very coarse one. It eliminated 99.9% of Reddit's corpus and still left thousands of candidates, so the surface was still choosing. Discovery lived inside that residual. A precise product search, by contrast, leaves nothing to choose; the system is a lookup table.

So the useful question is not "did the user ask for this?" but **how much of the choice did the user's request leave open, and did they use it?**

Replacing the subscribed feed with an algorithmic popular feed swapped a *user-set container* for a *platform-set container*. It did not add discovery — discovery was already happening inside my boundary. It removed the constraint that made the surface tolerable.

And I suspect the number that justified it was hit rate. "Users engage with only a small fraction of subscribed posts" reads as an underperforming feed, and the obvious fix is to expand supply. But a low hit rate inside a self-chosen container, with occasional deep engagement, is the *healthy state*. It is the slack that discovery needs. Optimising it upward consumes exactly the room the interesting thing was going to appear in.

## The same thing in a shop

Once this is a surface problem rather than a media problem, it shows up everywhere the same structure exists.

Take e-commerce, where topical diversity is nearly meaningless — every product on the page is similar. Search "running shoes," view twenty, click eight, wishlist three, buy one. That is the *ideal* behaviour. The surface did real work: it chose the twenty and ordered them, and I used what it offered.

Now the failure. I search a specific brand and model, click, buy. Or I search "whiteboard," take the first result, buy. In the first case the surface was given nothing to do. In the second it was given something to do and I did not use it. Either way the store contributed nothing to the decision — which means it is functioning purely as a delivery layer.

And a delivery layer is winnable by whoever delivers faster. If Amazon is only executing decisions I made elsewhere, I will make them on Blinkit instead the moment Blinkit stocks the item.

That reframes the entire measurement, and I think this is the version worth building: **this is a defensibility metric, not a quality metric.** It measures how much of the transaction the platform earned versus merely executed. Nobody buys a wellbeing metric. Everybody buys a defensibility metric.

It also gives the marketplace-versus-quick-commerce story an actual mechanism. Paid placement degrades the surface, discovery gets less rewarding, more customers arrive with decisions already made, more of the basket becomes commodity, and commodity baskets are won on delivery speed. The advertising revenue that starts the loop makes its early stages look excellent.

Worth noting what this says about quick commerce: it is not beating anyone at discovery. It is *deliberately zero-residual* — small assortment, ten-minute delivery, no browsing — competing precisely where the surface does not matter. Which gives a prediction I am willing to be judged on. As quick-commerce players expand assortment and add ad-funded placement, they acquire a surface they must then maintain, and they will inherit the exact decay they are currently exploiting.

## Temperature and structure

The last problem was that any per-user metric runs into a wall: people are legitimately different. Someone who engages deeply with a few things and someone who grazes broadly are both healthy. A metric that compares everyone to one ideal shape will flag half its users wrongly, and a metric that compares each user only to their own history will fire platform-wide every time a major news event changes everyone's behaviour at once.

The resolution is borrowed from physics. Across a family of distributions, temperature parameterises the whole range — hot is spread out, cold is concentrated — and every member of the family has the same structure. So a user's temperature is their operating point, and it carries no judgement. It moves constantly, and it should. The environment has a temperature too: a big event cools everyone simultaneously, and that is a state change, not a failure.

**Structure breaking is what defines the platform breaking.** Not the temperature. A distribution that no temperature can produce — mass at both extremes with nothing between, a truncated ladder where nothing ever escalates, a single item taking far more than any fit predicts — is a surface that has stopped working. And that test needs no history at all, which means it applies to a user on their first session.

Temperature shifts happen constantly at both the user and the platform level and should be ignored. Shape changing across many users at once is the signal.

## Why nobody does this

The measurement is not the hard part. The hard part is that any guardrail loses on effect size.

Raise ad load 10% and revenue moves 8% this quarter. The surface degrades by a fraction of a percent, which is inside the noise band of any two-week test. Every individual launch is defensible. The sum is not, and no single experiment can see the sum because the damage horizon is longer than the test horizon.

Two things fix that, both already in industrial use. **Cumulative budgets** — borrowed from reliability engineering, where each launch spends against an annual ceiling rather than being judged on its own significance, so the fifteenth launch of the year is refused on arithmetic instead of on judgement. And **long-term holdouts** — a cohort receiving none of the year's changes, held for quarters, against which an effect that was noise in every two-week test becomes unmissable.

Beyond that, three design constraints that separate the cases that worked from the case that did not:

A guardrail has to be a **hard constraint, not a weighted term in the objective** — otherwise the optimiser trades it away, which is its job. Hacker News penalises any post with more comments than upvotes and at least forty comments, scaling its score by the square of the votes-to-comments ratio, with moderators emailed on every trip so they can reverse false positives. That is comment volume outrunning endorsement treated as *evidence of a problem*. Facebook's MSI, by contrast, made "meaningful" a weight — and the proxy it chose for meaningful was comment volume, the exact quantity Hacker News penalises.

It has to be **computed from data outside the engagement loop**, or the loop corrupts it. Pinterest weights in-app surveys and manual quality assessment into ranking, on the stated view that engagement-only optimisation "will also, eventually, degrade a platform significantly."

And it has to be **held by someone who is not the optimiser**. Guardrails fail organisationally before they fail technically, because the team that owns the growth number also owns the guardrail and its exceptions.

Where the constraint has been applied properly, it works. Reddit's 2015 bans of its worst communities were studied across more than 100 million posts: more accounts than expected left the site entirely, those who stayed cut hate speech by at least 80%, and the communities that received the migrants showed no significant increase. Removal worked, and it did not merely displace the problem. YouTube reported a 70% drop in watch time of borderline content from non-subscribed recommendations in the US after 2019 — self-reported against a self-defined category and never independently verified, but the direction is a choice they made and could have not made.

Every successful case shares one thing. None of them tried to make polarising content less engaging. Each changed **what the ranker was permitted to count**. You cannot correct an objective from inside the objective.

And each had someone who could absorb the metric loss — a loss-leader, a pre-IPO cap table, an advertiser base that wanted safety. That is the real constraint. The fix is known and cheap. What is scarce is an owner who can afford to apply it.

## Where else this is happening

The structure generalises wherever two things hold: a **fixed-capacity surface** — user attention, shelf space, a room — and a **short-term goal focused on scale, valued enough that the operator will take a small hit on existing user behaviour.**

To which I would add a third, because the first two describe a reasonable business decision rather than a failure: **the cost is borne silently and never summed.** Incumbents do not complain. They go quiet, and then they leave.

Marketplaces. Exclusive membership programmes and clubs. Matchmaking. Search. App stores. Events. Tourism. Credentials and status symbols. Loyalty tiers, where the surface is purely rivalrous and growth destroys the product mechanically. Accelerators, where batch size runs against a fixed quantity of investor attention. Hostels and clubs and gyms, where the other customers *are* the product and a fixed room fills with a different mix than the one people came for.

Wherever the composition of who else is present determines the value of what you are buying, growth in participants degrades the surface, and the operator's growth metric cannot see it.

## The thing I keep coming back to

Some day I will start commenting far more than usual. Replying more, reposting more, arguing more. My engagement will spike.

To an engagement optimiser, that is the best day it has ever had with me.

It is also the moment I am closest to leaving.

The same event, read with opposite signs, by a system that has no way to tell the difference. Everything above is an attempt to build something that can.
