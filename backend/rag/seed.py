"""
Seed the vector store with built-in knowledge about Indian car insurance:
FAQs, product concepts, common objections, IRDAI rules.
"""
from __future__ import annotations
from .store import VectorStore
from .ingest import ingest_string


SEED_DOCS = {
    "faq_basics": {
        "name": "Car Insurance — Basics FAQ",
        "text": """
What is car insurance?
Car insurance is a financial protection product that covers losses due to accidents, theft, fire, natural calamities, and third-party liabilities for your vehicle. In India, having at least a third-party cover is mandatory under the Motor Vehicles Act, 1988.

What are the types of car insurance policies in India?
There are three main types:
1. Third-Party Liability Only — Covers damages to other vehicles, property, or injury to third parties. This is the legal minimum.
2. Comprehensive — Covers third-party liabilities plus own damage (accidents, theft, fire, natural disasters, etc.). Highly recommended for most owners.
3. Standalone Own-Damage — Covers only own damage, used alongside an existing third-party policy.

What does IDV mean?
IDV stands for Insured Declared Value. It is the current market value of your car, adjusted for depreciation. IDV is the maximum amount the insurer will pay in case of total loss or theft. A higher IDV means higher premium but better claim payout.

What is No Claim Bonus (NCB)?
NCB is a discount on the own-damage portion of your premium for each claim-free year. The slabs are:
- 1st claim-free year: 20%
- 2nd: 25%
- 3rd: 35%
- 4th: 45%
- 5th onwards: 50%
NCB is transferable when you switch insurers, but resets to 0 if you make a claim.

What is deductible / excess?
Deductible is the amount you pay out of pocket before the insurance kicks in. Compulsory deductible is set by IRDAI based on engine cc. You can opt for a voluntary deductible to reduce premium.

What is depreciation in car insurance?
Depreciation is the reduction in value of car parts over time. During a claim, the insurer deducts depreciation from parts cost unless you have a Zero Depreciation add-on.

Is car insurance mandatory in India?
Yes. Third-party liability insurance is legally mandatory. Driving without it is an offence under the Motor Vehicles Act and can result in fines up to ₹2,000 and/or imprisonment.
""",
    },
    "addons": {
        "name": "Add-on Covers Explained",
        "text": """
Zero Depreciation Cover (Bumper-to-Bumper)
Also known as zero-dep or bumper-to-bumper. Without this, insurers deduct depreciation (30-50% on plastic/fiber/rubber parts) from your claim payout. With Zero Dep, you get the full replacement cost. STRONGLY RECOMMENDED for cars less than 5 years old — saves typically ₹8,000 to ₹40,000 per claim. Costs 8-15% of base premium.

Return to Invoice (RTI)
If your car is stolen or declared total loss, standard insurance pays only IDV (depreciated value). RTI reimburses the full invoice value including ex-showroom price, road tax, and registration. BEST FOR cars less than 3 years old. Costs about 6% of base premium.

Engine Protect
Regular insurance covers accidents but NOT consequential damage like water ingression to engine (hydrostatic lock), lubricant leakage, or engine seizure. Engine Protect covers these. CRITICAL for flood-prone cities (Mumbai, Chennai, Bengaluru, Hyderabad). Engine repairs cost ₹50,000 to ₹3,00,000+.

24x7 Roadside Assistance (RSA)
Covers towing, flat tyre, fuel delivery, jump-start, lockout help, on-spot minor repairs. Costs ₹100-300/year. Highly recommended for long commutes or frequent highway trips.

Consumables Cover
Covers oils, nuts, bolts, grease, washers, coolant — which are NOT part of standard claims. Small but frequent savings.

NCB Protect
Protects your No Claim Bonus even if you make one or two claims in the year. Very useful if you have 25%+ NCB, since losing it means paying significantly higher premium next year.

Key & Lock Protect
Covers cost of replacing lost, stolen, or damaged car keys. Replacement of modern smart keys can cost ₹10,000-30,000.

Loss of Personal Belongings
Covers items like phones, laptops, bags lost during theft or break-in from your car. Usually capped at ₹25,000.

Tyre Protect
Covers accidental damage, cuts, bursts, and malicious acts on tyres and tubes (standard policy excludes these unless accident-related).

Compulsory Personal Accident (PA) Cover
MANDATORY under IRDAI rules. Covers ₹15 lakh for owner-driver in case of death or permanent disability from car accident. Cost ~₹675. Can be waived ONLY if you already have a valid ₹15L+ PA cover elsewhere.
""",
    },
    "objections": {
        "name": "Objection Handling Playbook",
        "text": """
Objection: "The premium is too expensive."
Response: Compare the daily cost. A ₹12,000 annual premium is just ₹33/day — less than a cup of coffee. Also compare to out-of-pocket cost of a single accident: a new bumper can cost ₹25,000+, engine repair ₹50,000-3L. Offer to show cheaper third-party or higher-deductible options.

Objection: "I'll renew later, my policy hasn't expired yet."
Response: That's fine — but renewing early locks in current prices (which rise 8-12% annually). Also, renewals done within 90 days of expiry preserve your NCB. Past that, NCB resets to 0 — losing 25-50% discount is a permanent cost.

Objection: "I don't need add-ons, my driving is careful."
Response: Add-ons aren't about driving skill — they cover risks you don't control. Zero Dep covers depreciation deducted during any claim. Engine Protect covers monsoon flooding. RTI covers theft. A single covered incident usually pays back 3-5 years of add-on cost.

Objection: "Which insurer is most trustworthy?"
Response: Look at the Claim Settlement Ratio (CSR) — % of claims paid vs received. Top insurers: Go Digit (97%), ICICI Lombard (96%), HDFC Ergo (96%), Zuno (96%). Also check network garages for cashless claims. Digital-first insurers (Digit, Acko, Zuno) have faster claim processing.

Objection: "Third-party only is cheaper, I'll go with that."
Response: Third-party is only ₹2,000-8,000 and covers liability to others — not damage to YOUR car. A single fender-bender you cause can cost ₹15,000-50,000 out of pocket. For cars over ₹5 lakh, comprehensive is standard advice.

Objection: "I want to compare with other apps first."
Response: Absolutely, comparison is smart. Most apps show similar insurer quotes — the real difference is add-on structure, claim support, and EMI options. Happy to answer specific comparison questions.

Objection: "Why is my premium higher than before?"
Response: Common reasons: (1) IDV increased with car appreciation or model upgrade, (2) NCB reset due to claim, (3) IRDAI third-party rate revisions, (4) add-ons added, (5) policy lapsed and NCB lost. Let me walk through your breakup.

Objection: "Cashless or reimbursement — which is better?"
Response: Cashless is strongly preferred — the insurer pays the garage directly and you pay only the deductible + non-covered items. Reimbursement means paying the full bill upfront and claiming later (with 3-15 day processing). Always ask for network garages near you.
""",
    },
    "claims": {
        "name": "Claims Process",
        "text": """
How to file a car insurance claim?
Step 1: Immediately after the incident, call the insurer's 24x7 toll-free helpline and note the claim number.
Step 2: File an FIR at the nearest police station for theft, third-party damage, or major accidents.
Step 3: Take photos/videos of the damage, accident scene, other vehicle (if any), and location.
Step 4: Tow the vehicle to a network (cashless) garage if possible.
Step 5: Submit claim form, RC, driving licence, policy doc, FIR copy, and photos.
Step 6: Insurer-appointed surveyor inspects and approves repair estimate.
Step 7: Garage does repair; insurer pays directly (cashless) or you pay and claim reimbursement.

What documents are needed for a claim?
- Claim form (from insurer or online)
- Copy of insurance policy
- Registration certificate (RC)
- Driving licence (valid, with correct vehicle class)
- FIR copy (for theft or major damage)
- Photos/videos of damage
- Repair estimate from garage
- Original repair bills (for reimbursement claims)
- KYC documents

How long does claim settlement take?
- Cashless claims: 24-72 hours after repair approval
- Reimbursement: 7-15 working days after submission of all documents
- Total loss / theft: 30-60 days after FIR and non-traceable certificate

What's NOT covered in car insurance?
- Regular wear and tear, mechanical breakdown, electrical failure (unaccident-related)
- Driving under influence of alcohol or drugs
- Driving without a valid driving licence
- Using a private car for commercial purposes (without commercial policy)
- Consequential damage (e.g., continuing to drive after hydrostatic lock)
- Damage outside geographic area defined in policy
- Intentional damage or illegal activity
""",
    },
    "regulatory": {
        "name": "Regulatory & Legal",
        "text": """
Motor Vehicles Act requirements:
Under Section 146 of the Motor Vehicles Act, 1988, every motor vehicle plying in a public place must have at least a third-party liability insurance policy. Driving without it is punishable with fine up to ₹2,000 or 3 months imprisonment, or both, for first offence.

IRDAI long-term TP rules (2018 onwards):
For new cars, buyers must purchase a 3-year third-party policy (bundled with 1-year own damage). Long-term TP locks in third-party premium for 3 years.

PUC certificate:
A valid Pollution Under Control (PUC) certificate is required to renew insurance under IRDAI Circular (May 2020). PUC is valid for 6 months (fresh vehicles) or 1 year (depending on state).

KYC / CKYC:
From April 2022, IRDAI mandates CKYC (Central KYC) verification for all insurance purchases. You'll need Aadhaar/PAN/Passport.

GST:
Insurance premiums attract 18% GST. Prices shown in summary should indicate if GST-inclusive or exclusive.

Grace period:
Most insurers offer a 30-day grace period after expiry where you can renew without losing NCB. After that, NCB resets to 0.

Car inspection requirement:
If the policy has lapsed beyond 90 days or there's a gap, insurers typically require a physical or photo-based car inspection before binding a new policy.
""",
    },
}


def seed_defaults(store: VectorStore) -> None:
    """Idempotently seed defaults. Adds a doc only if not already present."""
    existing_ids = {d["doc_id"] for d in store.list_docs()}
    for doc_id, doc in SEED_DOCS.items():
        if doc_id in existing_ids:
            continue
        chunks = ingest_string(doc["text"])
        store.add_chunks(doc_id=doc_id, doc_name=doc["name"], chunks=chunks, source="builtin")
