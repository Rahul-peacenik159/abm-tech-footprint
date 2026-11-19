# Who benefits from free tech-footprint data

## The test

> Can the seller see the buying signal from outside?

Free data helps most when the product someone sells, the competitor it replaces, or the tools it plugs into show up on a prospect's **website, DNS or subdomains**.

| Visibility | Where it shows | Free data works? |
|---|---|---|
| **High** | Scripts and widgets on the website: chat, booking, forms, video, analytics, checkout, reviews, consent banners | Yes, very well |
| **Medium** | DNS, email setup, SSO login pages, subdomains (`status.`, `docs.`, `apply.`, `order.`) | Yes |
| **Low** | Back-office: ERP, payroll, finance, core databases, PMS internals | No. Use job postings or paid data |

## Sellers who benefit most

| Seller type | What they can see on prospect sites | ABM play |
|---|---|---|
| **Hospitality tech** (booking engines, guest messaging, upsell, revenue capture) | Booking engine, chatbot, messaging widget, review widgets, RFP/venue tools | Replace a competitor's widget, or pitch hotels with no direct booking or chat at all |
| **Ecommerce apps** (reviews, search, pay-later, loyalty, subscriptions, SMS) | Shopify / BigCommerce / Magento, Klaviyo, Yotpo, Klarna / Affirm, Recharge | "You run Shopify + Klaviyo, here's our integration" |
| **Martech and adtech** (analytics, CDP, A/B testing, personalization) | GA4, Segment, Optimizely, VWO, ad pixels, tag managers | Score marketing maturity; replace a competitor |
| **Chat, forms and scheduling** | Intercom, Drift, HubSpot chat, Calendly, Chili Piper | Displacement; "no chat on your pricing page" gap |
| **Video platforms** | Wistia, Vidyard, Vimeo, YouTube embeds | Upgrade or replace the embedded player |
| **Web agencies and CMS vendors** | Outdated WordPress, slow PageSpeed, no tag manager | "Your site is costing you leads" audit |
| **Restaurant tech** | Toast, ChowNow, Olo, OpenTable, Resy, `order.` subdomains | Displacement; commission-saving pitch |
| **Auto dealer tech** | Dealer.com, DealerOn, Dealer Inspire platforms; chat; trade-in tools | Platform swap; add-on tools |
| **Healthcare and dental practice tech** | Online booking, patient intake, reviews, messaging | Practices with no online booking |
| **Higher ed tech** | Slate apply portals, chatbots, virtual tours | Enrollment-season timing |
| **Security, CDN and compliance** | Cloudflare / CDN headers, cookie consent tools, SSL setup | Compliance gap; renewal timing |
| **Email and deliverability tools** | MX and SPF: Google vs Microsoft, Mailchimp, SendGrid | Platform-fit lists; deliverability audits |
| **SaaS collaboration and identity** | TXT verification tokens: Atlassian, Slack, Zoom, DocuSign, Adobe, Microsoft 365 | Install-base targeting; competitive replacement |

## Target industries with the richest footprint

Businesses whose website **is** how they make money expose the most: hotels, ecommerce and DTC, restaurants, car dealers, clinics and dental groups, multifamily housing, universities, publishers, and SaaS companies themselves.

## The four plays the data unlocks

1. **Displacement:** they run a competitor's tool. Send a competitive sequence or competitor-conquest ads.
2. **Complement:** they run a tool you integrate with. Integration pitch, or partner co-sell with that vendor.
3. **Gap:** they're missing a category entirely. "You're leaving money on the table" message with a specific, checkable fact.
4. **Change:** a tool was added or removed since last scan. Timing trigger. A competitor disappearing is the strongest of all: they're switching right now.

Bonus: **maturity tiering.** Count of martech categories present (tag manager + CDP + A/B testing + marketing automation) is a decent proxy for budget and sophistication.

## Who it won't help much

Sellers of back-office software (HR, payroll, ERP, finance, internal security, data infrastructure). Their buying signals don't appear on websites. Point them to:

- job postings ("experience with Workday required" reveals the stack), the `abm-hiring-signals` bundle
- SEC filings and news, the `abm-public-company-triggers` and `abm-news-pulse` bundles
- paid technographic sources as an optional add-on

## How to apply this to your product in five minutes

1. Pick the closest pack in `stack-packs/` (or copy `_template.yaml`).
2. In its `seller:` block, list the tool ids you **replace** (`competitors`), the ones you **integrate with** (`complements`), and the categories a good-fit account should **have** (`must_have_categories`).
3. Rename the plays to match your actual sequences.
4. Scan 20 accounts you already know well. If the results match reality, scan the full list.
