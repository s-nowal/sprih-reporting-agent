"""Create (or verify) the 10-example LangSmith dataset for Research Agent evaluation.

Creates a multi-example dataset named ``research-agent-eval-10`` in LangSmith
covering 10 companies across diverse industries and query types. Safe to run
multiple times — skips silently if the dataset already exists.

Dataset layout
--------------
  inputs:  {"task": "<research prompt>"}
  outputs: {"reference_urls": [...]}

The test (``tests/evaluation/agents/research_agent/test_research_agent.py``)
reads ``reference_urls`` from the stored examples so that gold-standard sources
and scoring thresholds can be updated here without touching test code.

Usage
-----
    uv run python scripts/create_research_eval_dataset_10.py

Requires
--------
    LANGCHAIN_API_KEY (or LANGSMITH_API_KEY) set in ``.env`` or environment.
"""

from __future__ import annotations

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

# ---------------------------------------------------------------------------
# Dataset definition
# ---------------------------------------------------------------------------

DATASET_NAME = "research-agent-eval-10"

# Each example pairs a research task with gold-standard reference URLs.
# The LLM judge evaluates thematic coverage, not exact URL matches —
# a different year's report or an equivalent page counts as a valid hit.
# Reference URLs were last verified: 2026-04-09.
EXAMPLES = [
    # 1 — General ESG (Steel / Mining)
    {
        "inputs": {
            "task": "Research the ESG performance and sustainability practices of Tata Steel.",
        },
        "outputs": {
            "reference_urls": [
                "https://www.tatasteel.com/sustainability/",
                "https://www.tatasteel.com/investors/integrated-report-2024-25/pdf/Tata-Steel-IR-2024-25-BRSR-140725.pdf",
                "https://www.tatasteel.com/investors/integrated-report-2024-25/climate-change-report.html",
                "https://www.climateaction100.org/company-assessments/tata-steel-ltd/",
                "https://www.tatasteel.com/sustainability/esg-indicators-factsheet/",
            ],
            "reference_answer": (
                "Tata Steel's ESG strategy spans Environment, Social, and Governance pillars "
                "aligned with UN SDGs. Their FY2024-25 BRSR (62-page SEBI-mandated disclosure) "
                "covers Scope 1/2/3 emissions, energy intensity, water consumption, safety rates "
                "(TRIFR), workforce diversity, and board composition across India, UK, and "
                "Netherlands operations. Their climate change report is aligned with IFRS S2 "
                "(formerly TCFD) and TNFD, detailing decarbonization strategy, scenario analysis, "
                "and climate risk assessment. Climate Action 100+ rates Tata Steel across 11 "
                "net-zero benchmark indicators, showing partial compliance on most — particularly "
                "gaps in Scope 3 targets and capital allocation disclosure. The ESG indicators "
                "factsheet provides quantitative metrics covering 90% of global turnover "
                "(Tata Steel Limited, NINL, and European/SE Asian operations)."
            ),
        },
    },
    # 2 — Framework compliance (Consumer Goods)
    {
        "inputs": {
            "task": (
                "Research Unilever's alignment with TCFD and GRI reporting "
                "frameworks, including their latest disclosures."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.unilever.com/sustainability/responsible-business/reporting-standards/",
                "https://www.unilever.com/files/cdp-integrated-questionnaire-2024.pdf",
                "https://www.unilever.com/files/8b5df5f6-cb90-40fd-9691-38d06905d81d/unilever-climate-transition-action-plan-updated-2024.pdf",
                "https://www.climateaction100.org/company-assessments/unilever-plc/",
                "https://planet-tracker.org/unilevers-2024-climate-transition-update/",
            ],
            "reference_answer": (
                "Unilever reports 'in accordance' with GRI Standards (core option) and aligns "
                "with TCFD recommendations, WEF/IBC Stakeholder Capitalism Metrics, and CDP. "
                "Their reporting standards hub links to the GRI Content Index and TCFD disclosures "
                "within the Annual Report and Accounts. The 2024 Climate Transition Action Plan "
                "(CTAP) sets a 100% Scope 1/2 reduction target by 2030 and 42% Scope 3 reduction "
                "for energy/industrial processes, backed by a EUR 1B Climate & Nature Fund with "
                "executive remuneration linked to sustainability metrics. Their 2024 CDP Integrated "
                "Questionnaire covers climate change, forests, and water security. Climate Action "
                "100+ assesses Unilever on net-zero commitments and TCFD/IFRS S2 disclosure. "
                "Planet Tracker's independent analysis evaluates the CTAP's credibility, noting "
                "strengths in target-setting but scrutinizing delivery mechanisms."
            ),
        },
    },
    # 3 — Climate / environmental (IT Services)
    {
        "inputs": {
            "task": (
                "Research Infosys's carbon emissions targets, renewable energy "
                "usage, and climate action commitments."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://unfccc.int/climate-action/momentum-for-change/climate-neutral-now/infosys",
                "https://www.esgtoday.com/infosys-sets-new-goal-to-remove-more-carbon-than-it-emits-by-2030/",
                "https://www.there100.org/infosys",
                "https://sciencebasedtargets.org/companies-taking-action#table",
                "https://www.infosys.com/sustainability/documents/infosys-esg-report-2024-25.pdf",
            ],
            "reference_answer": (
                "Infosys has been carbon neutral since FY2020 (6th consecutive year) using a "
                "three-pillar strategy: energy efficiency (55% per-capita reduction since 2008), "
                "renewable energy (46.1 MW solar capacity, 44% renewable electricity sourcing), "
                "and carbon offsetting (benefiting 100,000+ rural families). Their ESG Vision 2030 "
                "targets carbon-negative status by 2030 — removing more GHGs than emitted — with "
                "a 90% Scope 1+2 reduction and 40% Scope 3 reduction from a 2020 baseline, "
                "validated by SBTi. Infosys was the first Indian company to join RE100 (committed "
                "to 100% renewable electricity), with plans for 30-40 MW additional solar PV "
                "expansion. The UNFCCC recognizes Infosys under its Climate Neutral Now initiative "
                "for contributions to 11 UN SDGs."
            ),
        },
    },
    # 4 — Competition / peer comparison (Energy / Conglomerate)
    {
        "inputs": {
            "task": (
                "Research how Reliance Industries compares to its peers in the "
                "Indian energy sector on ESG metrics and sustainability commitments."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.ril.com/sustainability",
                "https://www.climateaction100.org/company-assessments/reliance-industries-ltd/",
                "https://transitionpathwayinitiative.org/companies/reliance-industries",
                "https://archive.worldbenchmarkingalliance.org/publication/oil-and-gas/rankings/",
                "https://www.ril.com/ar2023-24/integrated-approach-to-sustainable-growth.html",
                "https://www.sustainalytics.com/esg-rating/reliance-industries-ltd/1008756619",
            ],
            "reference_answer": (
                "Reliance Industries has committed to net-zero carbon by 2035 and discloses ESG "
                "performance aligned with GRI, IIRC, GHG Protocol, and IPCC AR5 across Jio, "
                "Retail, O2C, and standalone RIL segments. However, third-party assessments reveal "
                "significant gaps vs. peers. Climate Action 100+ shows partial compliance on most "
                "indicators — particularly Scope 3 targets and capital allocation disclosure. The "
                "Transition Pathway Initiative rates RIL at Management Quality Level 3 ('Integrating "
                "into Operational Decision Making') with carbon performance disclosure rated "
                "'insufficient'. The World Benchmarking Alliance Oil & Gas Benchmark ranks RIL "
                "48th of 100 companies (total score 13.7/100, ACT score 8.7/60). Sustainalytics "
                "rates RIL's overall ESG risk as 'High' (36.5) despite 'Strong' management of "
                "material ESG risks. Compared to Indian energy peers (NTPC, ONGC, Adani), RIL has "
                "the most ambitious net-zero timeline but weaker third-party climate performance "
                "scores."
            ),
        },
    },
    # 5 — Supply chain sustainability (Fashion / Apparel)
    {
        "inputs": {
            "task": (
                "Research Patagonia's supply chain sustainability practices, "
                "including material sourcing and labor standards."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.bcorporation.net/en-us/find-a-b-corp/company/patagonia-inc/",
                "https://www.fairlabor.org/member/patagonia/",
                "https://www.fairtradecertified.org/blog/leading-with-fair-trade-how-patagonia-became-a-leader-in-ethical-sourcing/",
                "https://goodonyou.eco/how-ethical-is-patagonia/",
                "https://www.patagoniaworks.com/press/2025/11/11/patagonia-a-work-in-progress",
            ],
            "reference_answer": (
                "Patagonia is a certified B Corp (score 166.0 vs. 80 required, certified since "
                "2011) with strong supply chain accountability. They are FLA-accredited since 2008 "
                "with 81 monitored facilities across 14 countries, subject to third-party "
                "assessments and complaint investigations. Their decade-long Fair Trade partnership "
                "has generated $40M+ in Community Development Funds benefiting 80,000+ workers. "
                "Material sourcing includes recycled materials, organic cotton, and Bluesign-"
                "certified inputs, with a Global Recycled Standard certification. Good On You rates "
                "Patagonia 4/5 across Planet, People, and Animals; the Fashion Transparency Index "
                "scores them 41-50%. Their inaugural 'Work in Progress' report (Nov 2025) covers "
                "the Holdfast Collective ownership structure and FY2025 impact across responsible "
                "business practices, product sustainability, and activism. Notably, Patagonia does "
                "not file SEC reports, so third-party certifications and self-published reports are "
                "the primary disclosure channels."
            ),
        },
    },
    # 6 — Controversy / risk (Food & Beverage)
    {
        "inputs": {
            "task": (
                "Research ESG controversies and risks associated with Nestlé, "
                "including any regulatory actions or public criticism."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.nestle.com/sites/default/files/2025-02/creating-shared-value-nestle-2024.pdf",
                "https://www.business-humanrights.org/en/companies/nestl%C3%A9/",
                "https://systemicjustice.org/article/child-labor-in-the-global-cocoa-supply-chain-what-nestle-tells-us-about-corporate-harm/",
                "https://www.ethicalconsumer.org/company-profile/nestle-sa",
                "https://www.clientearth.org/latest/press-office/nestle-poland-sued-for-greenwashing/",
            ],
            "reference_answer": (
                "Nestlé faces significant ESG controversies across multiple dimensions. Child "
                "labor in the West African cocoa supply chain remains a persistent issue — Harvard "
                "Law/Systemic Justice analysis documents trafficking from Mali and Burkina Faso to "
                "unmonitored plantations, with structural barriers to corporate accountability. "
                "The Business & Human Rights Resource Centre tracks 49 response requests, 20+ "
                "allegations, and 5 attacks on human rights defenders linked to Nestlé; their "
                "KnowTheChain forced-labor benchmark score declined from 55/100 (2020) to 26/100 "
                "(2026). Ethical Consumer notes Nestlé was named a top-3 global plastic polluter "
                "for 5 consecutive years, documents anti-union practices in Colombia (12+ "
                "unionized employees killed since 1985), and the baby milk boycott has continued "
                "since 1988. In September 2025 ClientEarth sued Nestlé Poland for greenwashing "
                "over misleading '100% recycled PET' claims. Nestlé's own Creating Shared Value "
                "Report 2024 presents the company's counter-narrative on climate targets, "
                "regenerative agriculture, and social impact."
            ),
        },
    },
    # 7 — Governance focus (Financial Services)
    {
        "inputs": {
            "task": (
                "Research HDFC Bank's corporate governance practices, board "
                "diversity, and ESG-related risk management policies."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.hdfc.bank.in/about-us/corporate-governance",
                "https://www.hdfc.bank.in/about-us/board-of-directors",
                "https://www.hdfc.bank.in/esg",
                "https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/pdf/annual-reports/2024-25/HDFC_Bank_Annual_Report_2024_25-310202.pdf",
                "https://www.csrhub.com/CSR_and_sustainability_information/HDFC-Bank-Ltd",
            ],
            "reference_answer": (
                "HDFC Bank's governance structure includes a 13-member board with at least 3 "
                "women directors (Renu Sud Karnad, Sunita Maheshwari, Lily Vadera), providing "
                "gender and sectoral diversity across banking, public policy, and administration. "
                "The bank operates a multi-tiered ESG governance framework with a board-approved "
                "ESG Policy Framework (October 2024) that integrates ESG and climate change risk "
                "into credit appraisal and lending decisions. They target carbon neutrality by "
                "FY 2031-32 and have adopted renewable energy across operations. The Integrated "
                "Annual Report 2024-25 contains the Report on Corporate Governance (from page 280) "
                "and BRSR disclosures. The corporate governance portal covers 30+ sub-sections "
                "including codes of conduct, whistleblower policy, insider trading prevention, and "
                "committee compositions. CSRHub aggregates ratings from 29 sources (MSCI, ISS ESG, "
                "FTSE Russell, S&P Global) ranking HDFC Bank against 2,241 banking companies "
                "globally."
            ),
        },
    },
    # 8 — Sector-specific environmental (Automotive)
    {
        "inputs": {
            "task": (
                "Research Toyota Motor's environmental impact, including vehicle "
                "emissions standards, EV strategy, and manufacturing sustainability."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.toyota.com/usa/environmentalsustainability/goals-and-targets",
                "https://www.toyota-europe.com/electrification",
                "https://pressroom.toyota.com/toyota-releases-2025-north-american-environmental-sustainability-report/",
                "https://www.transitionpathwayinitiative.org/companies/toyota",
                "https://lobbymap.org/company/Toyota-Motor",
            ],
            "reference_answer": (
                "Toyota's Environmental Challenge 2050 sets six global targets spanning carbon "
                "neutrality, circular economy, and nature-positive outcomes, with 5-year action "
                "plans (current: FY2027-2031). Their multi-pathway electrification strategy "
                "covers BEV, PHEV, HEV, FCEV, and hydrogen — 35M+ electrified vehicles sold "
                "globally, 83% of models electrified, 24,000+ patents made freely available. "
                "In Europe, Toyota targets carbon neutrality by 2040; the North American "
                "sustainability report shows a 32% operational GHG reduction vs. 2019. The "
                "Transition Pathway Initiative rates Toyota at Management Quality Level 5 "
                "(highest tier) for climate governance. However, InfluenceMap's LobbyMap scores "
                "Toyota D+ (47%) for climate policy engagement, documenting lobbying against GHG "
                "emissions standards, ICE phase-out rules, and ZEV targets across multiple "
                "regions — a significant gap between stated commitments and policy advocacy. "
                "This tension between strong internal targets and weak external policy alignment "
                "is a key ESG finding."
            ),
        },
    },
    # 9 — Investment-grade ESG (Renewable Energy)
    {
        "inputs": {
            "task": (
                "Research Adani Green Energy's ESG profile for investment analysis, "
                "including ESG ratings, green bond issuances, and "
                "sustainability-linked financing."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.adanigreenenergy.com/sustainability",
                "https://www.adanigreenenergy.com/investors/investor-downloads",
                "https://www.adanigreenenergy.com/-/media/Project/GreenEnergy/Investor-Downloads/Green-Assurance-Report-AGEL/AGEL-Green-Financing-Framework.pdf",
                "https://www.sustainalytics.com/esg-rating/adani-green-energy-ltd/2004567447",
                "https://www.msci.com/research-and-insights/podcast/what-esg-tells-us-about-adani",
                "https://fortune.com/2023/02/19/esg-markets-shudder-as-adani-group-credit-arrangements-suggest-inadvertent-financing-of-heavy-polluters/",
            ],
            "reference_answer": (
                "Adani Green Energy (AGEL) presents a mixed ESG investment profile. On the "
                "positive side: 72.7M tonnes CO2 avoided, water-positive certification, FTSE/ISS "
                "ESG rankings, and Sustainalytics rates AGEL in the top 10 globally for renewable "
                "energy. The AGEL Green Financing Framework (August 2021) defines eligible project "
                "categories and reporting commitments; the investor downloads page hosts quarterly "
                "ESG compendiums, post-issuance Green Bond Information Reports (FY2021-22 through "
                "FY2024-25), and independent assurance statements. However, significant ESG risks "
                "exist: MSCI's analysis revealed governance vulnerabilities before the Hindenburg "
                "Research crisis, and Fortune reported that AGEL shares were pledged as collateral "
                "to finance the Carmichael coal mine — prompting Norway's largest pension fund "
                "(KLP) to divest and raising cross-subsidy concerns within the Adani conglomerate. "
                "Sustainalytics flags a 'significant controversy level' despite the strong sector "
                "ranking. Over 500 EU ESG funds held Adani stocks at the time of the controversy."
            ),
        },
    },
    # 10 — Social impact (Pharmaceuticals)
    {
        "inputs": {
            "task": (
                "Research Novartis's social impact initiatives, including "
                "access-to-medicine programs, clinical trial transparency, "
                "and health equity efforts."
            ),
        },
        "outputs": {
            "reference_urls": [
                "https://www.novartis.com/esg",
                "https://www.novartis.com/esg/access",
                "https://accesstomedicinefoundation.org/company/novartis-ag",
                "https://www.novartis.com/clinicaltrials/transparency",
                "https://www.novartis.com/news/media-library/novartis-society-integrated-report-2024",
                "https://www.novartis.com/esg/ethics-risk-and-compliance/human-rights",
            ],
            "reference_answer": (
                "Novartis ranks #1 in the 2024 Access to Medicine Index (score 3.78) with top "
                "marks in Governance of Access and R&D. Their access strategy covers value-based "
                "pricing, sustainable business models, a dedicated Sub-Saharan Africa strategy, "
                "oncology access programs, compassionate use, and licensing/donations. Clinical "
                "trial transparency has been a commitment since 2005 — they publish results "
                "publicly, provide patient-friendly summaries, and share anonymized data with "
                "qualified researchers through the NARD (Novartis Anonymized Redacted Dossiers) "
                "portal. The Novartis in Society Integrated Report 2024 comprehensively covers "
                "ESG performance and progress against targets. Their human rights framework "
                "addresses four priority areas (right to health, labor rights, environment, "
                "technology ethics) with due diligence processes, and they have been a UN Global "
                "Compact member since 2000. Supply chain assessments and grievance mechanisms "
                "complement the access-to-medicine focus."
            ),
        },
    },
]


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------

def main() -> None:
    """Create the 10-example LangSmith dataset if it does not already exist.

    Checks for an existing dataset by name before creating to make the script
    idempotent. Prints the dataset ID on creation or skips with a message.

    Raises:
        langsmith.LangSmithError: If the API key is missing or the request fails.
    """
    client = Client()

    # --- Check for existing dataset -----------------------------------------
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"Dataset '{DATASET_NAME}' already exists ({existing[0].id}) — skipping.")
        return

    # --- Create dataset + examples ------------------------------------------
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "ESG research agent evaluation — 10 diverse companies across "
            "industries and query types (general ESG, framework compliance, "
            "climate, peer comparison, supply chain, controversy, governance, "
            "sector environmental, investment ESG, social impact). "
            "Tests source coverage quality via LLM judge scoring."
        ),
    )
    client.create_examples(
        dataset_id=dataset.id,
        examples=EXAMPLES,
    )
    print(f"Created dataset '{DATASET_NAME}' ({dataset.id}) with {len(EXAMPLES)} examples.")


if __name__ == "__main__":
    main()
