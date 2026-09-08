"""Authoring source for 60 fictional procurement scenarios. Not a relevance-label generator.
The source guides identify places to verify evidence; they are NOT exhaustive gold targets.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prw.io import write_json, write_jsonl
ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://www.gov.uk/government/publications/procurement-act-2023-guidance-documents-'
SOURCES = {
 'payment': ('Guidance: Electronic Invoicing and Payment', BASE+'manage-phase/guidance-electronic-invoicing-and-payment-html'),
 'pipeline': ('Guidance: Pipeline Notice', BASE+'plan-phase/guidance-pipeline-notice-html'),
 'planned_notice': ('Guidance: Planned Procurement Notice', BASE+'define-phase/guidance-planned-procurement-notice-html'),
 'lots': ('Guidance: Lots', BASE+'define-phase/guidance-lots-html'),
 'transition': ('Guidance: transitional and saving arrangements', BASE+'plan-phase/guidance-transitional-and-saving-arrangements-html'),
 'direct': ('Guidance: Direct Award', BASE+'define-phase/direct-award-html'),
 'modification': ('Guidance: Contract Modifications', BASE+'manage-phase/guidance-contract-modifications-html'),
 'kpi': ('Guidance: Key Performance Indicators', BASE+'manage-phase/guidance-key-performance-indicators-html'),
 'participation': ('Guidance: Conditions of Participation', BASE+'procure-phase/guidance-conditions-of-participation-html'),
 'pme': ('Guidance: Preliminary Market Engagement', BASE+'define-phase/guidance-preliminary-market-engagement-html'),
 'framework': ('Guidance: Frameworks', BASE+'define-phase/guidance-frameworks-html'),
 'conflict': ('Guidance: Conflicts of Interest', BASE+'define-phase/guidance-conflicts-of-interest-html'),
 'valuation': ('Guidance: Valuation of Contracts', BASE+'define-phase/guidance-valuation-of-contracts-html'),
 'exclusion': ('Guidance: Exclusions', BASE+'procure-phase/guidance-exclusions-html'),
 'assessment': ('Guidance: Assessing Competitive Tenders', BASE+'procure-phase/assessing-competitive-tenders-html'),
 'dynamic': ('Guidance: Dynamic Markets', BASE+'define-phase/guidance-dynamic-markets-html'),
 'foi': ('ICO: Section 43 - Commercial interests', 'https://ico.org.uk/for-organisations/foi/freedom-of-information-and-environmental-information-regulations/section-43-commercial-interests/'),
 'collection': ('Procurement Act 2023 guidance collection', 'https://www.gov.uk/government/collections/procurement-act-2023-guidance-documents'),
 'pa': ('Procurement Act 2023', 'https://www.legislation.gov.uk/ukpga/2023/54/contents'),
 'pr': ('Procurement Regulations 2024', 'https://www.legislation.gov.uk/uksi/2024/692/contents'),
 'pcr': ('Public Contracts Regulations 2015', 'https://www.legislation.gov.uk/uksi/2015/102/contents'),
}
rows=[]; specs=[]; followups=[]

def add(split, suite, topic, key, situation, question, requirements, sources, regime='PA2023', missing=(), roles=None):
    index=sum(r['split']==split for r in rows)+1
    sid=('D' if split=='dev' else 'T')+f'{index:03d}'
    context = 'Assume an English public contracting authority and an above-threshold, non-exempt contract, not a utility, concession, defence or light-touch contract, unless the facts below expressly say otherwise.'
    public={'scenario_id':sid,'split':split,'scenario_group_id':key,'suite':suite,'topic':topic,
            'as_of':'2026-09-07','user_message':context+'\n\n'+situation+'\n\n'+question,'history':[],
            'synthetic':True,'authoring_status':'MODEL_AUTHORED_SOURCE_GUIDED_NOT_EXPERT_VALIDATED'}
    rows.append(public)
    req=[]
    for i, text in enumerate(requirements,1):
        policy = roles[i-1] if roles else ('OFFICIAL_ALLOWED' if suite=='guidance' else 'BINDING_REQUIRED')
        req.append({'id':f'R{i}','description':text,'mandatory':True,'source_policy':policy,
                    'allow_conditional':regime in ('UNCERTAIN','TRANSITIONAL') or bool(missing),
                    'assessment_unit':'atomic_information_requirement'})
    specs.append({'scenario_id':sid,'scenario_group_id':key,'split':split,'requirements':req,
                  'regime_context':regime,'missing_facts':list(missing),
                  'reference_source_ids':sources,'reference_targets_are_exhaustive':False,
                  'reference_status':'TOPIC_SOURCES_CHECKED_REQUIREMENT_LABELS_UNJUDGED',
                  'corpus_support_status':'NOT_ASSESSED','label_status':'UNJUDGED',
                  'author_note':'Requirements specify what evidence is needed, not a predetermined decision or closed list of correct chunks. Corpus gaps must remain visible.'})
    return sid

# DEV: 6 statutory, 7 semantic, 5 vocabulary, 6 multi-evidence,
#      5 applicability, 6 guidance, 2 authority, 3 compound.
add('dev','statutory','award_criteria','evaluation_weight_disclosure',
    'Our procurement team is preparing an office-equipment tender. The draft has three criteria but the scoring panel wants to decide their relative importance after bids arrive. I have been told to check section 23 of the Procurement Act 2023.',
    'Find the binding text governing when the assessment approach and relative importance must be set, and the information bidders need before preparing tenders.',
    ['The duty to set an assessment methodology for the award criteria.','The duty to state relative importance where multiple criteria are used.','The tender-information requirements relevant to bidder preparation.'],['assessment','pa'])
add('dev','statutory','kpi','kpi_new_contract_exception',
    'We are about to sign a new facilities-management public contract under the Procurement Act, with an estimated value above the statutory KPI trigger. The service director says performance is difficult to quantify and wants no published measures. I am checking section 52.',
    'Find the duty to set KPIs and any relevant exception, and distinguish setting them from later reporting performance.',
    ['The statutory duty and applicability conditions for setting KPIs.','The statutory exception relevant to meaningful assessment of performance.','The separate obligation concerning assessment and publication of performance.'],['kpi','pa'])
add('dev','statutory','valuation','value_renewal_options',
    'A department proposes an initial two-year equipment contract with two optional annual renewals and a separately priced installation service. The team has priced only the initial period. The finance lead asks for section 4 and Schedule 3.',
    'Retrieve the rules for estimating the relevant contract value, including options, associated payments and VAT treatment.',
    ['The link between the valuation obligation and the statutory valuation methodology.','Treatment of extension options and other amounts payable.','Treatment of VAT in the estimate.'],['valuation','pa'])
add('dev','statutory','contract_modification','legacy_extra_works',
    'A building contract was awarded under PCR2015 in 2024 and remains governed by those regulations. In 2026 the council proposes additional works, with no change to the contractor. The legal team specifically requests regulation 72.',
    'Find the applicable modification rules and evidence on when a new procurement would instead be necessary.',
    ['The regulation 72 route or routes relevant to the proposed modification.','Limits and conditions that distinguish a permitted modification from a new procurement.','Continuing application of the legacy regime to management of this contract.'],['pcr','transition'],regime='PCR2015')
add('dev','statutory','notices','direct_notice_contents',
    'A team has separately documented a permitted Procurement Act direct-award justification. It is now preparing the transparency notice and needs the actual legal source for what goes in it, not another explanation of possible direct-award grounds.',
    'Find the notice obligation and the Procurement Regulations provision specifying notice contents.',
    ['The statutory obligation to publish a transparency notice in the relevant direct-award context.','The secondary legislation specifying required transparency-notice information.'],['direct','pa','pr'])
add('dev','statutory','frameworks','open_framework_successions',
    'A public authority is designing an open framework and has been directed to section 49. Its draft permits reopening on materially different award criteria and has no clear schedule for successor frameworks.',
    'Retrieve the rules on successive frameworks, continuity of terms and the opening timetable.',
    ['The statutory concept of an open framework and successive frameworks.','Restrictions on the terms of successive frameworks.','The statutory rules governing when new suppliers can enter the scheme.'],['framework','pa'])

add('dev','semantic','procedure_selection','prototype_dialogue',
    'We need a new monitoring service but cannot yet specify which technical solution will work. We want shortlisted suppliers to demonstrate prototypes and discuss improvements before submitting final offers. No tender notice has been published.',
    'What procurement procedure could accommodate this, and what must be made clear before suppliers invest in participating?',
    ['Available competitive procedures and scope to design stages.','Transparency requirements for the proposed stages and supplier participation.','Constraints on assessment or refinement of award criteria during the procedure.'],['collection','assessment','pa'])
add('dev','semantic','participation','startup_accounts',
    'A young company can show current financial resources but does not have three years of audited accounts. Our draft tender requires three years from every bidder regardless of age. The contract concerns routine software support.',
    'Can that be a mandatory entry condition, and what proportionate alternatives should the team consider?',
    ['Legal limits on financial-capacity conditions and evidence requested.','Proportionality in relation to the contract rather than a universal policy.','Official explanation of alternative financial evidence for newer suppliers.'],['participation','pa'],roles=['BINDING_REQUIRED','BINDING_REQUIRED','OFFICIAL_ALLOWED'])
add('dev','semantic','exclusion','performance_single_incident',
    'A bidder missed one delivery milestone on an earlier public contract. The contract was completed after a short agreed extension; no damages or termination were imposed. A manager treats any previous delay as an automatic bar.',
    'What evidence and legal tests are needed before this history could justify exclusion from the new competition?',
    ['The relevant poor-performance exclusion ground and its conditions.','Assessment of continuing or recurring circumstances and remedial evidence.','The procedure for considering exclusion rather than automatic rejection.'],['exclusion','pa'])
add('dev','semantic','award_criteria','abnormally_low_cost',
    'One final tender is much cheaper than the rest. Evaluators suspect staffing assumptions are unrealistic but have not asked the bidder for an explanation. The preferred alternative costs substantially more.',
    'Can the low tender be discarded immediately, and what must the authority do first?',
    ['The rules on disregarding an abnormally low tender.','The opportunity to explain the price and assess that explanation.'],['assessment','pa'])
add('dev','semantic','conflict','relative_on_panel',
    'An evaluator discloses that their sibling works for a bidding supplier, although not on this tender. The tender notice has not yet been published. The team proposes simply recording the relationship and taking no further action.',
    'What must the authority identify, assess, mitigate and document before and during the procurement?',
    ['The duty to identify and keep conflicts under review.','The duty to take appropriate mitigation steps.','The conflicts-assessment requirement and timing.'],['conflict','pa'])
add('dev','semantic','frameworks','nonmember_calloff',
    'We want to buy from a capable local supplier through an existing Procurement Act framework, but that supplier is not a member. The team argues that this is allowed because it is only a small call-off.',
    'What restrictions determine who can receive a framework call-off, and what alternatives need consideration?',
    ['Limits on suppliers eligible for an award under the framework.','The difference between a framework call-off and an independently procured contract.'],['framework','pa'])
add('dev','semantic','market_engagement','incumbent_design',
    'Our incumbent helped explain an existing system during pre-tender discussions. They now wish to bid for its replacement. Some technical information from those discussions has not been shared with the wider market.',
    'How should we deal with any advantage, and does participation in those discussions require automatic exclusion?',
    ['Duties to avoid unfair advantage or distortion from preliminary engagement.','When exclusion becomes necessary and why prior participation alone is not sufficient.','Practical measures for sharing information and allowing preparation time.'],['pme','pa'],roles=['BINDING_REQUIRED','BINDING_REQUIRED','OFFICIAL_ALLOWED'])

add('dev','vocabulary','exclusion','ban_after_cartel_rumour',
    'A newspaper alleges that a bidder helped rivals take turns winning tenders. No decision or conviction is included in the report. A colleague asks us to blacklist the business today from all future purchases.',
    'What procurement evidence and decisions would be needed, and how is exclusion from this tender different from a wider ban?',
    ['Evidence needed to identify a relevant competition-related exclusion ground.','The authority-level exclusion process and recurrence assessment.','The distinction between procurement exclusion and ministerial debarment.'],['exclusion','collection','pa'])
add('dev','vocabulary','valuation','slice_purchase',
    'A buyer suggests chopping a planned multi-site furniture purchase into separate orders so each stays under the advertising threshold. The sites have coordinated requirements and the purchasing plan is already agreed.',
    'Can we value each order separately for that reason, and what should be recorded in the valuation decision?',
    ['Restrictions on artificial subdivision or valuation to avoid the Act.','Aggregation rules and the role of genuine reasons for separate treatment.'],['valuation','pa'])
add('dev','vocabulary','dynamic_markets','approved_list_contract',
    'Our team wants a rolling approved-supplier list for repair services. Qualified firms should be able to join whenever they are ready. A manager assumes that getting on the list automatically wins a contract.',
    'Which Procurement Act arrangement fits that design, and how does membership differ from winning an individual job?',
    ['The legal structure of a dynamic market and access for new suppliers.','The separate procedure for awarding contracts by reference to membership.'],['dynamic','pa'])
add('dev','vocabulary','award_criteria','green_points_unrelated',
    'A stationery tender proposes green points for each bidder having an unrelated overseas environmental charity programme. There is no requirement linking that programme to producing or delivering the stationery.',
    'Can we use that as a winning score, and what makes an environmental award criterion lawful?',
    ['Required connection of award criteria to the contract subject matter.','Clarity, specificity and proportionality requirements for criteria.'],['assessment','pa'])
add('dev','vocabulary','lots','smaller_packages_access',
    'We are buying routine cleaning for several sites. Smaller firms say they could cover individual sites but not the whole requirement. The team wants to make smaller bidding packages, while one manager confuses this with splitting purchases to avoid procurement law.',
    'What must we consider about lots, and how does legitimate packaging differ from avoiding the valuation rules?',
    ['Duty to consider whether the requirement can appropriately be awarded in lots.','Reasons and information relevant to a decision on lots.','Distinction between using lots and artificial subdivision for threshold avoidance.'],['lots','valuation','pa'])


add('dev','multi_evidence','direct_award','failed_mandatory_spec',
    'An open competition for specialist equipment produced bids that all failed an essential technical requirement. We have not established whether a different competitive approach could work. The authority wants to negotiate with one former bidder and sign this week.',
    'What must be established before switching route, what supplier checks remain, and what publication is needed before award?',
    ['Conditions for switching from competitive tendering to direct award.','Applicable supplier exclusion or suitability checks on that route.','The pre-award transparency-notice obligation.'],['direct','exclusion','pa','pr'])
add('dev','multi_evidence','direct_award','technical_lockin_evidence',
    'We need replacement components for an existing technical installation. Its manufacturer says only it can supply compatible parts, but the buyer has not checked independent alternatives. There is no immediate emergency.',
    'What direct-award justification could be relevant, what evidence must support it, and what transparency steps would follow?',
    ['The statutory direct-award gateway and relevant technical-competition justification.','Conditions concerning alternatives and the origin of the lack of competition.','Publication obligations that remain if direct award is justified.'],['direct','pa','pr'])
add('dev','multi_evidence','contract_modification','known_risk_flood',
    'A works tender and awarded contract described a specific ground-condition risk. That risk has now occurred without either party causing it. The proposed change would increase price and extend the works programme; the team has not compared a new procurement.',
    'What evidence is needed to justify modifying for that risk, and which publication duties must be assessed separately?',
    ['Conditions of the known-risk modification ground.','Applicable limits and justification for modification instead of a new procurement.','Contract-change notice and publication requirements, including exceptions.'],['modification','pa','pr'])
add('dev','multi_evidence','exclusion','essential_subcontractor',
    'A shortlisted prime contractor relies on a specialist subcontractor to satisfy a technical condition. Evidence has emerged that the subcontractor may fall within an exclusion ground. The prime proposes replacing it without changing the tender.',
    'How does the subcontractor affect the prime, and what procedure and opportunity to replace must be considered?',
    ['How associated persons or relevant subcontractors affect exclusion assessment.','Procedure and opportunity for replacement before an exclusion decision.','Whether the replacement still establishes the required participation capacity.'],['exclusion','participation','pa'])
add('dev','multi_evidence','market_engagement','engagement_no_notice',
    'A council held supplier workshops before preparing a tender. It did not publish a preliminary engagement notice and shared different information at different meetings. The tender notice is due for publication tomorrow.',
    'What must it do about unequal information and the missing engagement notice, and what record should it retain?',
    ['Steps to address unfair advantage arising from the engagement.','Notice or explanation obligations relevant to the missing engagement notice.','Official guidance on maintaining and sharing an engagement record.'],['pme','pa'],roles=['BINDING_REQUIRED','BINDING_REQUIRED','OFFICIAL_ALLOWED'])
add('dev','multi_evidence','kpi','publish_performance_confidential',
    'We manage a new Procurement Act contract above the KPI trigger and have set several material performance indicators. The supplier says its disappointing results are confidential and asks us to publish none of them.',
    'Which performance information must be considered for publication, and how should an asserted confidentiality exception be evaluated?',
    ['The performance-assessment and publication duty.','Selection of relevant KPIs or notice content requirements.','The statutory grounds and limits for withholding publication information.'],['kpi','collection','pa','pr'])

add('dev','applicability','transition','planning_not_launch',
    'The council approved a business case in January 2025 and spoke informally to suppliers. It did not publish a contract notice or invite tenders until March 2025. The team says the January business case means PCR2015 must apply.',
    'Which event determines the transition in this situation, and which regime should the team investigate?',
    ['The legally relevant commencement trigger under the transitional rules.','Distinction between internal preparation and starting a procurement for transitional purposes.'],['transition','pa','pcr'],regime='TRANSITIONAL')
add('dev','applicability','transition','old_framework_new_calloff',
    'An existing framework was advertised and awarded under PCR2015 in 2024. In 2026 we want to use it for a new call-off. A template automatically inserts Procurement Act notices because of the present year.',
    'Which regime applies to the call-off and its notices, and what framework facts must be verified?',
    ['Transitional treatment of call-offs under legacy frameworks.','Applicable legacy framework and publication rules rather than calendar-year substitution.','The need to verify use is within the framework terms and validity.'],['transition','pcr'],regime='PCR2015')
add('dev','applicability','transition','legacy_kpi_demand',
    'A services contract worth more than the new KPI trigger was awarded under PCR2015 in 2023. Its manager has been told to add Procurement Act KPIs and statutory KPI notices because the contract is still running in 2026.',
    'Does the new statutory KPI regime apply to that contract merely because it continues, and what distinction should the manager make?',
    ['Transitional treatment of performance management on legacy contracts.','Distinction between statutory new-regime obligations and contractual performance arrangements.'],['transition','kpi','pcr'],regime='PCR2015')
add('dev','applicability','jurisdiction','scottish_only_council',
    'A devolved Scottish council is procuring ordinary local services for its own use. It is not using another authority\'s framework or acting in a cross-border arrangement. A colleague offers an English Procurement Act checklist.',
    'What jurisdiction question must be resolved before relying on that checklist, and how should the answer be limited if Scottish sources are absent?',
    ['The territorial and authority scope of the Procurement Act.','The need for applicable Scottish procurement sources and disclosure of any corpus gap.'],['collection','pa'],regime='SCOTLAND',roles=['BINDING_REQUIRED','OFFICIAL_ALLOWED'])
add('dev','applicability','transition','contract_date_unknown',
    'Our contract register shows a 2025 signature date but the original procurement file is missing. A manager wants advice on changing the contract and assumes the signature date alone selects the Procurement Act.',
    'Which missing facts are needed to choose the legal regime, and what conditional modification guidance can be given meanwhile?',
    ['Transitional facts needed beyond the signature date.','Conditional identification of new and legacy modification regimes without an unjustified final choice.'],['transition','modification','pcr'],regime='UNCERTAIN',missing=['How the procurement was commenced','Whether it was a framework call-off'])

add('dev','guidance','market_engagement','small_business_workshop',
    'We are planning market engagement for a routine service. Small suppliers say an all-day in-person event would be costly. The team wants an accessible engagement process without giving a selected group an advantage.',
    'Find practical official guidance on engagement formats, information sharing and fair access.',
    ['Accessible and proportionate engagement formats.','Practical steps for equal access to relevant information.','Record keeping appropriate to the engagement process.'],['pme'])
add('dev','guidance','participation','financial_risk_operating_process',
    'A procurement officer has financial statements and recent management accounts from several suppliers. They need a practical process to assess financial capacity consistently, with decisions related to the actual delivery risk rather than arbitrary turnover hurdles.',
    'Find official guidance explaining how to structure that assessment and avoid disproportionate barriers.',
    ['Practical selection of relevant financial-capacity evidence.','Assessment proportionality to delivery risk and contract characteristics.','Recording and communicating the chosen assessment approach.'],['participation','collection'])
add('dev','guidance','planning','pipeline_preparation',
    'A large authority is preparing its annual procurement pipeline. It expects payments above the statutory annual-spend trigger, but its draft lists only new contract awards and ignores expenditure under existing contracts. The team needs a practical way to prepare and maintain the notice.',
    'Find official guidance on the spending calculation, which forthcoming procurements belong in the pipeline and how updates should be handled.',
    ['Which payments are relevant to the annual-spend assessment.','Which planned procurements and reporting period are relevant to the notice.','Practical publication and updating guidance.'],['pipeline'])

add('dev','guidance','kpi','performance_dashboard',
    'A contract manager has twelve operational service measures and needs to decide which are meaningful performance indicators rather than administrative activity counts. They want a practical approach for a new Procurement Act contract.',
    'Find guidance on choosing useful indicators, setting expectations and identifying material measures for reporting.',
    ['The role of KPIs in assessing contractual outcomes.','Practical selection of meaningful and material measures.','How KPI selection relates to ongoing performance reporting.'],['kpi'])
add('dev','guidance','confidentiality','foi_supplier_consultation',
    'A council has received an FOIA request for a supplier pricing schedule. The supplier says disclosure would harm future bids but has given no explanation. The FOI officer wants an assessment process, not a blanket refusal template.',
    'Find regulator guidance on consultation, evidence of commercial prejudice and the public-interest balance.',
    ['Obtaining specific evidence of the alleged commercial harm.','Assessing the relevant prejudice threshold rather than assuming sensitivity is enough.','Applying the public-interest test.'],['foi'],regime='FOIA')
add('dev','guidance','payment','invoice_processing_workflow',
    'An authority receives valid, undisputed electronic invoices under a new Procurement Act contract. Its internal finance process starts the payment clock only after the service manager approves the invoice, which may take several weeks. Staff need a compliant operating process.',
    'Find official guidance on receipt, validation, disputes and payment timing, including what staff should tell suppliers.',
    ['How receipt and the payment period are treated.','Timely handling of invalid or disputed invoices rather than unexplained internal delay.','Communication of invoicing and payment arrangements to suppliers.'],['payment'])


add('dev','authority','direct_award','consultant_urgency_claim',
    'A consultant says any urgent requirement can be directly awarded because a law-firm article mentions urgency. We know only that the internal deadline is tight. The legal adviser requests the binding sources rather than commentary.',
    'Retrieve the statutory gateway and urgency conditions, making clear what facts must be established.',
    ['Binding direct-award gateway relevant to an urgency justification.','The specific statutory conditions and limitations of that justification.','Missing factual matters that prevent treating internal urgency alone as sufficient.'],['direct','pa'],missing=['Cause of urgency','Foreseeability','Practicable competition timetable'])
add('dev','authority','confidentiality','wrong_section43_instrument',
    'Our FOI officer asks whether commercial pricing can be withheld under section 43 of the Freedom of Information Act 2000. A search system has returned section 43 of the Procurement Act because both texts discuss public procurement.',
    'Retrieve the binding FOIA provision and regulator explanation applicable to commercial interests, not procurement procedure switching.',
    ['The correct statutory instrument identity for FOIA section 43.','Relevant commercial-interest exemption and public-interest requirements.','ICO explanation supporting the disclosure decision process.'],['foi'],regime='FOIA',roles=['BINDING_REQUIRED','BINDING_REQUIRED','OFFICIAL_ALLOWED'])

add('dev','compound','unknown_context','urgent_supplier_preference',
    'A service manager writes: We need this purchase soon and prefer the incumbent. Can we skip competition? They have not provided the authority type, contract value, original procurement history or reason for urgency.',
    'What facts do you need before advising, and what general procurement routes should be checked without assuming permission?',
    ['Facts needed to establish scope, regime and any exemption.','Facts needed to test a direct-award justification rather than mere preference.','Conditional framework for next steps without an unsupported approval.'],['direct','transition','valuation','pa'],regime='UNCERTAIN',missing=['Authority type','Value','Procurement history','Objective justification'],roles=['OFFICIAL_ALLOWED','BINDING_REQUIRED','OFFICIAL_ALLOWED'])
add('dev','compound','participation_and_award','capacity_and_scoring_mix',
    'A team designing a maintenance procurement wants to exclude firms with low turnover, award extra points for the same turnover, and let panel members adjust those points after interviews. The proposed conditions and criteria have not yet been published.',
    'Separate these decisions and identify the evidence needed to make each defensible.',
    ['Proportionate financial-capacity conditions of participation.','Separation of supplier capacity assessment from tender award criteria.','Rules governing methodology disclosure or refinement during the procedure.'],['participation','assessment','pa'])
add('dev','compound','contract_modification','extension_reason_missing',
    'A contract manager asks to extend an arrangement by two years and add a new service. They cannot yet provide the original term, extension options, value, applicable procurement regime or details of the added service.',
    'Which documents and facts must be obtained, and what modification questions can only be answered conditionally?',
    ['Facts establishing applicable regime and original contractual options.','Tests concerning value, duration and scope under the relevant modification rules.','Publication questions that depend on the eventual justification and change.'],['modification','transition','pcr'],regime='UNCERTAIN',missing=['Original maximum term','Options','Value','Regime','Nature of added service'])

# TEST: genuinely different decision situations, not wrapper paraphrases.
add('test','statutory','award_criteria','refine_after_participation',
    'A competitive flexible procurement has completed its participation stage. The authority wants to refine a quality criterion before inviting final tenders. It believes section 24 allows unlimited changes because suppliers have not submitted their final prices.',
    'Find the binding restrictions on refinement and what must have been communicated to suppliers.',
    ['The statutory circumstances in which award criteria may be refined.','Limits on refinement and required disclosure to suppliers.'],['assessment','pa'])
add('test','statutory','conflict','assessment_before_market_creation',
    'An authority is preparing the notice establishing a dynamic market. No individual contract competition has begun. The project team considers a conflicts assessment unnecessary until the first contract is advertised and asks specifically about section 83.',
    'Retrieve the rule on assessment timing for establishing the market and the required contents of that record.',
    ['When the conflicts assessment must be prepared in relation to the dynamic market notice.','What the conflicts assessment must record.'],['conflict','dynamic','pa'])
add('test','semantic','frameworks','calloff_conditions_new',
    'A multi-supplier framework permits the buying authority to assess technical capability for each call-off. The buyer proposes an additional participation condition unrelated to the work and would use it to avoid inviting an unpopular framework member.',
    'What constrains the call-off condition and the selection process?',
    ['Rules on conditions of participation in framework call-off selection.','Required relationship and proportionality of the condition to contract performance.','Compliance with the framework selection process.'],['framework','participation','pa'])
add('test','semantic','exclusion','self_cleaning_after_conviction',
    'A bidder discloses a relevant historic fraud conviction involving a connected person. It has replaced management, compensated affected parties and introduced independent controls. The tender team believes a historic conviction makes those steps irrelevant.',
    'What must be assessed before deciding the bidder\'s status, including the effect of remedial evidence?',
    ['The relevant mandatory exclusion framework and connection to the supplier.','Assessment of whether relevant circumstances continue or are likely to recur.','How remedial measures and evidence enter the statutory assessment.'],['exclusion','pa'])
add('test','semantic','valuation','unquantifiable_usage',
    'A public authority plans a demand-led service with no stated quantity limit. It has historical usage information but claims it is impossible to value the future contract, so the buyer intends to classify it as below threshold.',
    'How should uncertainty be handled when estimating value, and what rule applies if an estimate genuinely cannot be made?',
    ['The obligation to estimate maximum payable value using available information.','The statutory consequence where contract value cannot be estimated.'],['valuation','pa'])
add('test','vocabulary','notices','announce_winner_sign_today',
    'A team says it has picked a winner for a new competitive public contract and wants to sign today. The losing suppliers have not received assessment information. The manager calls any waiting time a courtesy cooling-off period.',
    'What steps and waiting rules need checking between the award decision and entering the contract?',
    ['Assessment-summary or related bidder-information duties before award.','Contract award notice requirements.','The standstill rules and relevant exceptions.'],['collection','pa','pr'])
add('test','vocabulary','exclusion','bidder_peeked_rival',
    'A bidder obtained another bidder\'s confidential price breakdown during this competition and used it in its revised offer. The team calls it sharp practice and wants to know whether ordinary low scoring is enough.',
    'What procurement rule addresses an unfair advantage from this conduct, and what must be established before excluding it?',
    ['Improper behaviour and unfair advantage in the particular procurement.','Conditions and process for the statutory treatment of the affected supplier.'],['exclusion','pa'])
add('test','vocabulary','dynamic_markets','closed_roster_reopen',
    'An authority has already established a dynamic market for building maintenance. A qualified new business asks to join, but the team wants to shut the roster for a year to save administrative effort.',
    'Can membership be closed that way, and what is the proper approach to a new application?',
    ['Obligation to keep a dynamic market open to new suppliers.','Rules for considering qualifying membership applications.'],['dynamic','pa'])
add('test','multi_evidence','direct_award','flood_immediate_short_bridge',
    'Unexpected flooding has damaged a public building and temporary protective work is needed immediately. The team proposes a direct award covering both emergency protection and a five-year refurbishment programme. Procurement under an accelerated competition may be possible for the later works.',
    'What limits distinguish an emergency direct award from the wider planned work, and which notice obligations need assessment?',
    ['The urgency justification and its factual conditions.','Limits relating to necessity and the scope or duration of the urgent award.','Publication requirements relevant to the permitted route.'],['direct','pa','pr'])
add('test','multi_evidence','contract_modification','supplier_restructure_novation',
    'A supplier reorganises its business and proposes transferring a Procurement Act public contract to a newly formed group company. Contract price and services would not change. The team thinks no procurement or publication checks are necessary because the price is unchanged.',
    'What legal ground, supplier checks and transparency requirements must be considered for the transfer?',
    ['The corporate-restructuring modification ground and restrictions on changing supplier.','Exclusion-related condition applicable to the replacement supplier.','Contract-change notice and publication requirements for this type of modification.'],['modification','exclusion','pa','pr'])
add('test','multi_evidence','market_engagement','cancel_after_workshop_only',
    'A council has published a preliminary market engagement notice and held workshops but has not published a tender or transparency notice. Funding is withdrawn. It wants to stop while leaving an intelligible public record.',
    'What is legally required at this stage, and what additional communication or record keeping is recommended?',
    ['Whether the statutory procurement-termination notice duty is triggered by these facts.','Official guidance on voluntary communication and recording reasons when engagement does not proceed.'],['pme','collection','pa'],roles=['BINDING_REQUIRED','OFFICIAL_ALLOWED'])
add('test','multi_evidence','kpi','partial_termination_reporting',
    'A new Procurement Act contract above the KPI trigger has persistent performance failures. The authority is considering ending only one service element while retaining the rest. The contract manager needs to distinguish performance reporting from termination reporting.',
    'What evidence explains the reporting duties for poor performance and the relevance of partial rather than full termination?',
    ['Performance-assessment and notice duties relevant to poor performance.','The distinction between partial termination reporting and full contract termination.','Required information or timing for the relevant notices.'],['kpi','collection','pa','pr'])
add('test','applicability','transition','legacy_dps_extension',
    'A dynamic purchasing system was established under PCR2015 before the Procurement Act commenced. In September 2026 its manager proposes extending its lifetime for several more years and describes it as a new-regime dynamic market.',
    'Which transitional restrictions apply to extending the legacy system, and can changing its label change the applicable rules?',
    ['Transitional limits on extending and ending a legacy dynamic purchasing system.','Distinction between the existing legacy arrangement and establishing a Procurement Act dynamic market.'],['transition','dynamic','pcr'],regime='TRANSITIONAL')
add('test','applicability','transition','legacy_direct_award_first_contact',
    'Before 24 February 2025 the authority formally contacted a supplier with the intention of awarding a contract without prior publication under a PCR2015 exception. The contract was not signed until later. The buyer has retained the dated correspondence and wants to know which notice regime applies.',
    'Which transitional commencement rule is relevant to this non-advertised procurement, and what facts in the correspondence matter?',
    ['The transitional trigger for a procurement without prior publication.','Evidence of the pre-commencement intention and action rather than relying solely on signature date.','Consequent regime for the relevant notices.'],['transition','pcr'],regime='TRANSITIONAL')
add('test','applicability','confidentiality','foi_not_new_procurement',
    'An FOIA request made in 2026 concerns pricing in a contract awarded in 2022. The team says no disclosure is possible because Procurement Act publication duties do not apply retrospectively to that contract.',
    'Which disclosure regime governs the request, and why does the absence of a new-regime publication duty not decide the FOIA question?',
    ['FOIA duties and exemptions relevant to the request.','Separation between disclosure on request and procurement publication obligations.','Commercial-prejudice and public-interest assessment appropriate to the current request.'],['foi','transition'],regime='FOIA')
add('test','guidance','frameworks','framework_user_due_diligence',
    'A procurement officer has been offered access to a third-party framework. They have only a marketing brochure and cannot see the permitted buyers, suppliers, scope or call-off rules. They want a practical checking list before recommending its use.',
    'Find official guidance on checks a buying authority should make before using the framework.',
    ['Checking that the authority can use the framework and that the proposed purchase is in scope.','Checking the permitted suppliers and applicable call-off selection procedure.','Obtaining the actual terms rather than relying on marketing assurances.'],['framework'])
add('test','guidance','planning','planned_notice_not_tender',
    'The authority published a planned procurement notice only two weeks before it expects to publish its tender notice. Staff want to use the shortest possible tendering period and think the advance notice itself invited bids. The requirement is complex and involves unfamiliar suppliers.',
    'Find official guidance distinguishing advance notice from a call for competition and explaining when any timetable reduction can be used responsibly.',
    ['Purpose of a planned procurement notice and its distinction from inviting tenders.','Conditions for a qualifying planned procurement notice and timetable reduction.','Need to consider adequate bidder preparation rather than automatically use a minimum period.'],['planned_notice'])

add('test','authority','exclusion','minister_vs_council_debarment',
    'A council procurement officer wants to place a supplier on the national debarment list after excluding it locally. An internal note treats the two decisions as interchangeable. The adviser asks for the statutory allocation of powers.',
    'Retrieve binding evidence distinguishing the authority\'s procurement decision from the ministerial debarment process.',
    ['The contracting authority\'s role in applying exclusion in a procurement.','The statutory role and process for ministerial debarment.'],['exclusion','collection','pa'])
add('test','authority','participation','mandatory_insurance_at_bid',
    'A tender template requires every bidder to have expensive project-specific insurance before submitting an offer. Smaller bidders say they can obtain it if awarded the contract. A consultant says the template is binding policy.',
    'Find the statutory restriction relevant to insurance timing and distinguish it from internal policy.',
    ['The binding restriction concerning insurance as a participation requirement.','Relationship between proportionate contractual risk protection and procurement-stage evidence demands.'],['participation','pa'])
add('test','compound','framework_and_change','calloff_scope_user_unknown',
    'A public body wants to join an arrangement described only as a framework, add a service not mentioned in the brochure and extend the supplier\'s work for several years. The officer does not know when the framework was set up, its users, its scope or whether any contract has already been awarded.',
    'Which facts and evidence are needed before deciding whether this is a valid call-off, a modification or a separate procurement?',
    ['Facts determining regime and eligibility to use the arrangement.','Evidence distinguishing an in-scope call-off from a new purchase.','Facts and legal tests for any modification of an already awarded contract.'],['framework','transition','modification','pa','pcr'],regime='UNCERTAIN',missing=['Establishment date and regime','Eligible buyers','Scope','Existing contract status'])

# Follow-ups are fixed fact changes, never generated from which system failed.
F = [
 ('D008','The bidder can now provide a bank guarantee and a current cash-flow forecast. Reassess the evidence needed without assuming these are automatically sufficient.', ['Proportionate evaluation of alternative financial evidence.','Remaining checks on actual capacity to deliver.'], ['participation']),
 ('D010','The low bidder has now supplied a detailed explanation showing a different delivery method. What must evaluators assess before accepting or rejecting that explanation?', ['Evaluation of the explanation for a low tender.','Decision linked to the statutory test rather than price difference alone.'], ['assessment']),
 ('D011','The evaluator has withdrawn from scoring. Does that end the need to keep the conflict under review?', ['Continuing conflict-review duties after one mitigation step.','Assessing and documenting whether remaining risks have been addressed.'], ['conflict']),
 ('D019','The team has now documented why no suitable tender was received, but the selected supplier may meet a discretionary exclusion ground. Does switching route remove the supplier checks?', ['Applicable supplier checks when switching to direct award.','Treatment of the potential exclusion ground and recurrence evidence.'], ['direct','exclusion']),
 ('D025','Correction: a contract notice was actually published on 10 February 2025. Our previous description that the first notice was in March was wrong. Reassess the regime.', ['Effect of the corrected procurement commencement fact on transitional applicability.','Use of the corrected fact rather than persisting with the previous assumption.'], ['transition']),
 ('D029','We found the file: the contract is a call-off from a framework awarded under PCR2015 in 2024. What evidence is now relevant to modification?', ['Legacy framework call-off transitional treatment.','Applicable legacy modification rules.'], ['transition','pcr']),
 ('D034','The supplier now identifies an imminent retender and explains a specific pricing harm. Does that guarantee withholding all the requested information?', ['Fact-specific prejudice assessment based on the supplier explanation.','Public-interest balance and consideration of separate parts of the requested information.'], ['foi']),
 ('D040','The original contract expressly provides for one extra year, not two. We still do not know the procurement regime. What can and cannot be concluded?', ['Significance of the limited original extension option.','Unresolved regime and modification conditions preventing an unconditional conclusion.'], ['modification','transition','pcr']),
 ('T002','The market notice was published yesterday without an assessment. Does the fact that no contract has yet been awarded eliminate the need to address the omission?', ['Timing of conflicts-assessment duty for market establishment.','Need to address the omission without assuming absence of contract award cures it.'], ['conflict','dynamic']),
 ('T010','The proposed transferee is now reported to be an excluded supplier. What does this change about the restructuring route?', ['Effect of excluded-supplier status on the restructuring modification ground.','Need to verify the status and legal conditions before transfer.'], ['modification','exclusion']),
 ('T015','The supplier has added a confidentiality clause signed in 2022. Does the clause by itself decide the FOIA request?', ['Effect and limits of a confidentiality clause under FOIA.','Case-specific exemption and public-interest assessment.'], ['foi']),
 ('T020','We obtained the terms: the body is an eligible framework user, but the extra service is outside the stated scope. No call-off has yet been awarded. How does that narrow the options?', ['Effect of scope limits on a proposed call-off.','Distinction between procuring a new requirement and modifying a contract that does not yet exist.'], ['framework','modification'])
]
for base_id, message, reqs, sources in F:
    base=next(r for r in rows if r['scenario_id']==base_id)
    fid=base_id+'-F1'
    followups.append({'scenario_id':fid,'parent_scenario_id':base_id,'split':base['split'],'scenario_group_id':base['scenario_group_id'],'suite':'followup','topic':base['topic'],'as_of':base['as_of'],
                      'user_message':message,'history':[{'role':'user','content':base['user_message']}],
                      'history_protocol':'fixed_user_only_history_no_system_generated_answers','synthetic':True})
    specs.append({'scenario_id':fid,'scenario_group_id':base['scenario_group_id'],'split':base['split'],
                  'requirements':[{'id':f'R{i+1}','description':t,'mandatory':True,'source_policy':'OFFICIAL_ALLOWED','allow_conditional':True,'assessment_unit':'atomic_information_requirement'} for i,t in enumerate(reqs)],
                  'reference_source_ids':sources,'regime_context':'FOLLOWUP_DEPENDENT','missing_facts':[],
                  'reference_targets_are_exhaustive':False,'reference_status':'TOPIC_SOURCES_CHECKED_REQUIREMENT_LABELS_UNJUDGED',
                  'corpus_support_status':'NOT_ASSESSED','label_status':'UNJUDGED'})

if __name__=='__main__':
    assert len(rows)==60 and sum(r['split']=='dev' for r in rows)==40
    for split, folder in [('dev','dev'),('test','test_sealed')]:
        write_jsonl(ROOT/'data'/folder/'scenarios.jsonl', [r for r in rows if r['split']==split])
        write_jsonl(ROOT/'data'/folder/'requirements.jsonl', [s for s in specs if s['split']==split and '-F' not in s['scenario_id']])
        write_jsonl(ROOT/'data'/folder/'followups.jsonl', [r for r in followups if r['split']==split])
        write_jsonl(ROOT/'data'/folder/'followup_requirements.jsonl', [s for s in specs if s['split']==split and '-F' in s['scenario_id']])
    write_json(ROOT/'references'/'source_registry.json', {'checked_on':'2026-09-07','note':'Topic orientation verified on official pages. Not a corpus-availability audit or exhaustive legal gold. source URLs are locator aids, not pre-awarded relevance.',
        'sources':[{'id':k,'title':v[0],'url':v[1],'scope':'official_legislation_or_guidance'} for k,v in SOURCES.items()]})
    print('Wrote', len(rows), 'base scenarios and', len(followups), 'fixed user-only follow-ups')
