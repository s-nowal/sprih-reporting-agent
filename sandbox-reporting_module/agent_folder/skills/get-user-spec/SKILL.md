---
name: get-user-spec
description: Details process for getting tone and style preferences from the user for an ESG report. Use the skill before index generation.
---

# ESG Tone Specification

Your task is to get the tone that the user wants in their ESG report.

You MANDATORILY have to ask for specifications across the following:
1. Language Formality - Corporate or legal formal / Simple, formal / Conversational
2. Promotional Intent - Proud, Confident / Neutral / Humble
3. Creativity - Creative / Standard
4. Financial Aspect - No Financial Disclosures / Limited Financial Disclosure / Integrated Finance
5. Disclosing Gaps - No gap disclosures / Targeted gap disclosures / Full gap disclosure
6. Length - Brief, dense / Medium-length / Long report

## General Instructions
1. One by one, you must offer the user the options to choose along with 1 example (except for Financial Aspect).
2. Do not give definitions unless the user asks. If the user does not know or is unsure or wants to skip the question, choose the default option. Let the user know which is the default option.
3. You can let the user add a new option/specify something.

---

## Language Formality

You MUST offer the user the option to choose between the following options:

1. **Corporate/Legal Formal:** Written primarily for legal or regulatory audiences, not general readers. Language that prioritises precision and compliance over readability. Characterised by passive constructions, multi-clause sentences, and institutional vocabulary.

    Example 1: Our company is committed to fostering an environment in which all personnel are authorized and enabled to exercise judgment and make decisions in a manner consistent with established corporate values and in furtherance of our strategic objectives.

2. **Simple, formal, neutral**: Language written for informed stakeholders and general audience. It is professional and precise without being inaccessible. Direct sentence structure, active voice, no hedging, readable without being casual.

    Example 1: Our company strives to ensure that all employees are empowered to make decisions consistent with our values and can collectively support our business purpose.

3. **Conversational:** Language written for the general reader. Direct, plainspoken, and personal without sacrificing substance (content remains serious and informed). Interactive language that is written to build connection with the reader.

    Example 1: Everyone within our company should feel the freedom to make choices that align with the company values and work toward our shared purpose.

Default option is "Simple, formal, neutral": Option 2.

---

## Promotional Intent

You MUST offer the user the option to choose between the following options:

1. **Proud/Confident Tone:** Emphasizes achievements, progress, and leadership with clear ownership. Uses assertive and positive language to highlight outcomes and impact, while remaining grounded in verifiable data. Conveys momentum and credibility without exaggeration.

    Example 1: "Driven by sustained investment in on-site solar and long-term power purchase agreements, we achieved a 60% renewable energy share in FY 2023-24, up from 42% the prior year, keeping us firmly on track for our 2030 net-100% target."

2. **Neutral Tone:** Presents information in a factual, objective manner with minimal interpretation. Focuses on data, processes, and outcomes without signaling judgment, emphasis, or sentiment. Prioritizes clarity and precision over narrative.

    Example 1: "Renewable energy accounted for 60% of total energy consumption in FY 2023-24, up from 42% in FY 2022-23, reflecting continued investment in on-site solar capacity and long-term power purchase agreements. This trajectory is in alignment with our 2030 net-100% target."

3. **Humble Tone:** Acknowledges progress while maintaining a measured and reflective stance. Recognizes limitations, ongoing challenges, or areas for improvement, and avoids overstating impact. Emphasizes learning, responsibility, and continuous improvement.

    Example 1: "Renewable energy represented 60% of our energy mix in FY 2023-24, up from 42% the prior year. While we remain on track for our net-100% 2030 target, the remaining 40% remains a complex transition challenge that we are currently working to address."

Default option is "Proud/Confident Tone": Option 1.

---

## Creativity

You MUST offer the user the option to choose between the following options:

1. **Creative:** Use of engaging, distinctive, or narrative-driven titles and quotations that go beyond standard reporting labels to capture attention and reinforce messaging. Note: Even in creative mode, some must follow standard titles. Example: GRI Index, etc.

2. **Standard:** Use of conventional, widely accepted titles and minimal or no quotations, aligned with common ESG reporting frameworks and structures.

    Examples:
    - (Creative) "From Earth to Elegance" → (Standard) "Mining Operations"
    - (Creative) "Materials Matter" → (Standard) "Product Sourcing"
    - (Creative) "Telling Stories that drive change" → (Standard) "Our Newsletter", etc.

Default option is "Standard": Option 2.

---

## Financial Aspect

You MUST offer the user the option to choose between the following options:

1. **No Financial disclosures:** No information about revenue or finances in the full report.

2. **Limited / Segregated Finance:** The report discusses financial information only within dedicated financial sections (e.g., revenue, financial performance) and does not meaningfully connect financial considerations to sustainability initiatives or outcomes.

3. **Integrated Finance:** The report explicitly connects financial strategy and mechanisms to sustainability goals, positioning finance as a tool to drive ESG outcomes and long-term value creation.

    Example:
    - Qualitative: Talk of financial institutions used (banks), the use of finance as a lever for change, the focus of the business on the finance-sustainability tradeoff, etc.
    - Quantitative: % of revenue earned donated/spent via CSR Initiatives/allocated for sustainability, etc.

Default option is "Limited / Segregated Finance": Option 2.

---

## Disclosing Gaps

You MUST offer the user the option to choose between the following options:

1. **No gap disclosures:** No mention of any initiative/reporting/coverage NOT done by the company.

    Example 1: "In FY2024, we recorded Scope 1 emissions of 12,400 tCO₂e and Scope 2 emissions of 8,200 tCO₂e."

2. **Targeted gap disclosures:** Highlighting gaps in initiatives/reporting ONLY if the company can state formulated and verifiable plans to cover those gaps in the future.

    Example 1:
    - CASE 1: There is a clear plan to address it in the future.
        "In FY2024, we recorded Scope 1 emissions of 12,400 tCO₂e and Scope 2 emissions of 8,200 tCO₂e. We recognise that a complete picture of our carbon footprint must include value chain emissions. To that end, we have engaged [Firm/Partner]/ initiated to conduct a Scope 3 disclosure practices and materiality assessment in H1 2025, with full category-level reporting targeted for our FY2025 disclosure."

    - CASE 2: There is no plan for addressing lack of coverage in the future.
        "In FY2024, we recorded Scope 1 emissions of 12,400 tCO₂e and Scope 2 emissions of 8,200 tCO₂e."

3. **Full gap disclosure:** Highlighting gaps despite structured readdressment plans being present or not.
    NOTE: Full gap disclosure option MUST have the following facets:
    - The overall frame must be positive: the section must contain statements detailing awareness and effort ("We know there is more work to do", etc.).
    - The missing data must be framed more at the scope of the problem than the scope of the company. (Eg: Missing emission data should not be tied to the shortcomings/lack of awareness in the company, but the scale of the problem → Difficulty in collection due to vastness of supply chain, etc.).
    - For negative/unwanted trends in data, look for external and geopolitical reasons that may have caused the trend. You must remember that disclosure must NEVER hurt the reputational capital of the company.

    Example 1: "In FY2024, we recorded Scope 1 emissions of 12,400 tCO₂e and Scope 2 emissions of 8,200 tCO₂e. We are committed to transparency and know there is more work ahead of us. Comprehensive Scope 3 measurement remains one of the most complex challenges across the industry: the breadth of global supply chains, the variability in supplier reporting maturity across geographies, and the absence of standardised primary data collection frameworks make consistent, auditable value chain accounting an evolving discipline for companies of our scale and reach. We are actively engaged with industry working groups and continue to invest in the data infrastructure and supplier partnerships needed to bring this reporting forward. We remain committed to expanding our emissions disclosure as methodologies and data availability mature."

Default option is "Targeted Gap Disclosures": Option 2.

---

## Length

You MUST offer the user the option to choose between the following options:

1. **Brief, dense report:** Focuses on concise, data-driven sections with minimal narrative. Emphasis is placed on presenting key metrics, disclosures, and outcomes clearly and efficiently, ensuring no critical facts or figures are omitted.

    Example 1: "We undertook a comprehensive stakeholder consultation process in FY 2023-24 as part of the double materiality assessment process. This entailed capturing the views of ~120 stakeholder including: ~45 external stakeholders representing sustainability experts, civil society organisations, B2B customers, third party manufacturers, logistics partners, media and institutional investors. More than 70 internal stakeholders covering sustainability practitioners and senior management representatives were also consulted."

2. **Medium-length report:** Maintains a balance between context and data. Sections clearly articulate the company's intent, values, and ethics, etc. while integrating relevant performance metrics, outcomes, and analytical insights.

    Example 1: "Understanding the concerns of those we impact and those who impact us is fundamental to identifying what matters most. In FY 2023-24, our double materiality assessment brought together ~120 stakeholders across two broad groups. Internally, more than 70 sustainability practitioners and senior management representatives ensured our priorities were anchored in organizational reality. Externally, ~45 participants, spanning sustainability experts, civil society organisations, B2B customers, third-party manufacturers, logistics partners, media, and institutional investors, widened the lens to capture societal and market expectations. These enlightening engagements allowed us to re-evaluate and re-define our priorities for the upcoming financial year."

3. **Long report:** Adopts a detailed, narrative-driven approach. Sections provide comprehensive coverage of strategies, initiatives, and objectives, supported by data at key points, with a strong emphasis on values, impact, and long-term vision.

    Example 1: "At XYZ Company, we understand the essential role of meeting stakeholder expectations in driving our organization's success and recognize that engaging meaningfully with stakeholders allows us to gain valuable insights into their key concerns and expectations.

    These considerations drive our commitment to fostering an open, responsive, and ongoing dialogue with all stakeholders, emphasizing a collaborative approach to value creation through strong, lasting relationships. To fulfill these commitments, we engaged in a comprehensive double materiality assessment in FY 2023-24.

    Our internal stakeholders include our dedicated in-house talent, covering sustainability practitioners and senior management representatives. More than 70 of these professionals were engaged through suitable channels. Moreover, we engaged ~45 external stakeholders such as sustainability experts and civil society organisations. Key members of our value chain such as our B2B customers, third party manufacturers, logistics partners, media and institutional practitioners were also engaged in many open discussions pertaining to their concerns and expectations."

Default option is "Medium-length report": Option 2.

---

## Output Format

Once all specifications are resolved, you must write an md report with the content in the following format:

```
# [Name of specification]

## Chosen option by user (can contain a new option defined by user)
- Definition of chosen option (with notes from this prompt, if any defined)
- Any custom additions made by user
- Example of chosen option

# [Name of specification], etc.
```

---

## Universal Tone Guidelines

These apply to all ESG reports regardless of the tone choices made above. INCLUDE THIS AS_IS IN THE REPORT.

### Navigational Clarity
1. Ensure the report is easily navigable with a clear structure and logical flow across sections and subsections.
2. Provide links to previously published reports and those released within the same financial year.
3. Include links to relevant third-party platforms (e.g., SBTi) for transparency and verification.

### Showing Awareness
1. Acknowledge relevant external challenges (e.g., environmental degradation, economic volatility, regulatory shifts) impacting the business.
2. Demonstrate awareness of systemic risks to long-term sustainability, while maintaining a neutral and non-political tone.
3. Emphasize the company's responsibility and role in addressing these challenges through its operations, strategy, and purpose.

### Storytelling/Narration
1. Ensure a strong storytelling narrative with a clear, logical, and engaging flow across the report.
2. Incorporate past, present, and forward-looking context to show progression and continuity.
3. Use interactive elements (e.g., rhetorical questions, section prompts) to engage the reader.
4. Structure content using storytelling formats (e.g., "How it started → How it's going", "How it works") to improve clarity and relatability.
5. Embed narrative continuity within sections by linking decisions, actions, and outcomes over time.

### Linking to Sustainability
1. Link all sections of the report to the overarching sustainability objectives.
2. Ensure each disclosure is clearly aligned with identified material topics.
3. Maintain consistent mapping between actions, metrics, and materiality priorities across the report.

### IMPORTANT
1. No unsubstantiated claims without evidence.
2. Results and metrics mapped to disclosures should be kept technical and be verified.