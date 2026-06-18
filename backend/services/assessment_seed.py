"""
Seed sample assessment questions for all 10 specialties.
6 realistic medical coding questions per specialty = 60 total.
Only called when the assessment_questions table is empty.
"""
from sqlalchemy.orm import Session
from models import AssessmentQuestion


SEED_QUESTIONS = [
    # ─── ICD-10-CM ────────────────────────────────────────────────────────────
    dict(
        question_id="ICDX-001", specialty="ICD10CM",
        question_text="A patient is diagnosed with Type 2 diabetes mellitus with diabetic chronic kidney disease, stage 3. What is the correct ICD-10-CM code sequence?",
        option_a="E11.22, N18.3", option_b="E11.65, N18.3", option_c="E13.22, N18.3", option_d="E11.29, N18.9",
        correct_answer="A", difficulty="Easy", topic="Diabetes", question_type="Conceptual",
    ),
    dict(
        question_id="ICDX-002", specialty="ICD10CM",
        question_text="Acute appendicitis without abscess and without peritonitis. Select the correct ICD-10-CM code.",
        option_a="K35.80", option_b="K35.2", option_c="K37", option_d="K35.89",
        correct_answer="A", difficulty="Easy", topic="Abdominal", question_type="Conceptual",
    ),
    dict(
        question_id="ICDX-003", specialty="ICD10CM",
        question_text="A patient has essential hypertension and chronic kidney disease stage 3. Which ICD-10-CM code sequence applies?",
        option_a="I12.9, N18.3", option_b="I10, N18.3", option_c="I12.9 only", option_d="I10 only",
        correct_answer="A", difficulty="Medium", topic="Cardiovascular", question_type="Rule-based",
    ),
    dict(
        question_id="ICDX-004", specialty="ICD10CM",
        question_text="Sepsis due to Methicillin-resistant Staphylococcus aureus (MRSA). What is the correct ICD-10-CM code?",
        option_a="A41.02", option_b="A41.01", option_c="A49.02", option_d="A41.9",
        correct_answer="A", difficulty="Medium", topic="Sepsis", question_type="Conceptual",
    ),
    dict(
        question_id="ICDX-005", specialty="ICD10CM",
        question_text="When coding an inpatient admission for pneumonia with incidental Type 2 DM with hyperglycemia, which condition is the principal diagnosis?",
        option_a="Pneumonia", option_b="Type 2 DM with hyperglycemia", option_c="Hyperglycemia alone", option_d="Both are principal diagnoses",
        correct_answer="A", difficulty="Hard", topic="Guidelines", question_type="Rule-based",
    ),
    dict(
        question_id="ICDX-006", specialty="ICD10CM",
        question_text="Major depressive disorder, single episode, severe without psychotic features. Correct ICD-10-CM code?",
        option_a="F32.2", option_b="F32.1", option_c="F33.2", option_d="F32.3",
        correct_answer="A", difficulty="Medium", topic="Mental Health", question_type="Conceptual",
    ),

    # ─── Surgery ─────────────────────────────────────────────────────────────
    dict(
        question_id="SURG-001", specialty="Surgery",
        question_text="Which CPT code represents a laparoscopic appendectomy?",
        option_a="44970", option_b="44950", option_c="44960", option_d="44979",
        correct_answer="A", difficulty="Easy", topic="Laparoscopic", question_type="Conceptual",
    ),
    dict(
        question_id="SURG-002", specialty="Surgery",
        question_text="Open repair of initial inguinal hernia, reducible, patient age 5 years or older. Correct CPT code?",
        option_a="49505", option_b="49500", option_c="49507", option_d="49520",
        correct_answer="A", difficulty="Medium", topic="Hernia", question_type="Conceptual",
    ),
    dict(
        question_id="SURG-003", specialty="Surgery",
        question_text="Arthroscopic partial medial meniscectomy, right knee. CPT code?",
        option_a="29881", option_b="29880", option_c="29882", option_d="29876",
        correct_answer="A", difficulty="Medium", topic="Orthopedic", question_type="Conceptual",
    ),
    dict(
        question_id="SURG-004", specialty="Surgery",
        question_text="A surgeon performs a laparoscopic cholecystectomy with intraoperative cholangiography. How many CPT codes are reported?",
        option_a="One code (47563 includes cholangiography)", option_b="Two codes", option_c="Three codes", option_d="One code with a modifier",
        correct_answer="A", difficulty="Hard", topic="Laparoscopic", question_type="Scenario",
    ),
    dict(
        question_id="SURG-005", specialty="Surgery",
        question_text="Which modifier is appended to indicate a procedure performed on the left side?",
        option_a="-LT", option_b="-RT", option_c="-50", option_d="-51",
        correct_answer="A", difficulty="Easy", topic="Modifiers", question_type="Conceptual",
    ),
    dict(
        question_id="SURG-006", specialty="Surgery",
        question_text="A surgeon performs concurrent bilateral inguinal hernia repairs, initial, reducible. How is this coded?",
        option_a="49505-50", option_b="49505 x2 units", option_c="49505 and 49500", option_d="49525-50",
        correct_answer="A", difficulty="Hard", topic="Bilateral", question_type="Rule-based",
    ),

    # ─── ED Facility ─────────────────────────────────────────────────────────
    dict(
        question_id="EDFC-001", specialty="ED Facility",
        question_text="An ED facility assigns a Level 5 E&M code (99285). Which condition must be met?",
        option_a="High complexity medical decision making or high severity presenting problem", option_b="Moderate complexity MDM", option_c="Low complexity MDM", option_d="Straightforward MDM",
        correct_answer="A", difficulty="Medium", topic="E&M Levels", question_type="Rule-based",
    ),
    dict(
        question_id="EDFC-002", specialty="ED Facility",
        question_text="For facility coding, which revenue code is used for the ED visit level?",
        option_a="045x", option_b="036x", option_c="071x", option_d="025x",
        correct_answer="A", difficulty="Easy", topic="Revenue Codes", question_type="Conceptual",
    ),
    dict(
        question_id="EDFC-003", specialty="ED Facility",
        question_text="A patient presents to the ED with a chief complaint of chest pain. EKG, troponins x2, and chest X-ray are ordered. The patient is admitted. How is the ED visit billed by the facility?",
        option_a="Bill the appropriate ED E&M level; no separate observation code", option_b="Bill observation codes only", option_c="Bill both ED E&M and observation", option_d="Bill only the admission H&P",
        correct_answer="A", difficulty="Hard", topic="Guidelines", question_type="Scenario",
    ),
    dict(
        question_id="EDFC-004", specialty="ED Facility",
        question_text="Which HCPCS code is reported for a facility critical care service for patients older than 5 years?",
        option_a="99291", option_b="99292", option_c="99293", option_d="99295",
        correct_answer="A", difficulty="Medium", topic="Critical Care", question_type="Conceptual",
    ),
    dict(
        question_id="EDFC-005", specialty="ED Facility",
        question_text="A laceration repair is performed in the ED. Which modifier tells the payer the procedure was performed in the emergency department setting?",
        option_a="-27 (multiple outpatient E&M same day)", option_b="-25", option_c="-57", option_d="-59",
        correct_answer="A", difficulty="Easy", topic="Modifiers", question_type="Conceptual",
    ),
    dict(
        question_id="EDFC-006", specialty="ED Facility",
        question_text="Under APC packaging, which of the following is typically packaged into the ED E&M APC?",
        option_a="Low-cost ancillary services such as simple labs", option_b="Radiology procedures", option_c="Surgical procedures", option_d="Chemotherapy drugs",
        correct_answer="A", difficulty="Hard", topic="APC Packaging", question_type="Rule-based",
    ),

    # ─── ED Profee ────────────────────────────────────────────────────────────
    dict(
        question_id="EDPF-001", specialty="ED Profee",
        question_text="A physician documents a comprehensive history, comprehensive exam, and high complexity MDM for an ED patient. What CPT code is assigned?",
        option_a="99285", option_b="99284", option_c="99283", option_d="99282",
        correct_answer="A", difficulty="Easy", topic="E&M Levels", question_type="Conceptual",
    ),
    dict(
        question_id="EDPF-002", specialty="ED Profee",
        question_text="Modifier -25 is appended to an ED E&M code when:",
        option_a="A significant, separately identifiable E&M service is performed on the same day as a procedure", option_b="A bilateral procedure is performed", option_c="A procedure is performed by two surgeons", option_d="A decision for surgery is made",
        correct_answer="A", difficulty="Medium", topic="Modifiers", question_type="Rule-based",
    ),
    dict(
        question_id="EDPF-003", specialty="ED Profee",
        question_text="A physician spends 45 minutes providing critical care services in the ED (exclusive of separately reportable procedures). What codes are reported?",
        option_a="99291 only (first 30-74 minutes)", option_b="99291 + 99292", option_c="99291 x2", option_d="99292 only",
        correct_answer="A", difficulty="Medium", topic="Critical Care", question_type="Rule-based",
    ),
    dict(
        question_id="EDPF-004", specialty="ED Profee",
        question_text="Which of the following is NOT a component of medical decision making in the 2023 E&M guidelines?",
        option_a="Physical examination", option_b="Number and complexity of problems addressed", option_c="Amount/complexity of data reviewed", option_d="Risk of complications",
        correct_answer="A", difficulty="Hard", topic="MDM Guidelines", question_type="Conceptual",
    ),
    dict(
        question_id="EDPF-005", specialty="ED Profee",
        question_text="Under 2023 AMA E&M guidelines, time-based coding in the ED is based on:",
        option_a="Total time spent on the day of the encounter, including non-face-to-face work", option_b="Face-to-face time only", option_c="Time documenting the note only", option_d="Time spent with nursing staff",
        correct_answer="A", difficulty="Medium", topic="Time-Based Coding", question_type="Rule-based",
    ),
    dict(
        question_id="EDPF-006", specialty="ED Profee",
        question_text="A patient is seen in the ED and is determined to require surgery the next morning. Which modifier is appended to the E&M code?",
        option_a="-57", option_b="-25", option_c="-24", option_d="-26",
        correct_answer="A", difficulty="Easy", topic="Modifiers", question_type="Conceptual",
    ),

    # ─── Ancillary ────────────────────────────────────────────────────────────
    dict(
        question_id="ANCL-001", specialty="Ancillary",
        question_text="A patient receives physical therapy evaluation and treatment on the same day. Modifier appended to the evaluation code?",
        option_a="-KX (meets medical necessity criteria)", option_b="-59", option_c="-25", option_d="-GP",
        correct_answer="A", difficulty="Medium", topic="PT Modifiers", question_type="Rule-based",
    ),
    dict(
        question_id="ANCL-002", specialty="Ancillary",
        question_text="Which HCPCS code is used for a standard wheelchair, not otherwise classified?",
        option_a="K0001", option_b="K0002", option_c="K0003", option_d="E1230",
        correct_answer="A", difficulty="Easy", topic="DME", question_type="Conceptual",
    ),
    dict(
        question_id="ANCL-003", specialty="Ancillary",
        question_text="A patient undergoes a complete transthoracic echocardiogram with Doppler. CPT code?",
        option_a="93306", option_b="93307", option_c="93308", option_d="93303",
        correct_answer="A", difficulty="Medium", topic="Cardiology", question_type="Conceptual",
    ),
    dict(
        question_id="ANCL-004", specialty="Ancillary",
        question_text="When reporting radiology services, the technical component is identified by modifier:",
        option_a="-TC", option_b="-26", option_c="-52", option_d="-59",
        correct_answer="A", difficulty="Easy", topic="Radiology Modifiers", question_type="Conceptual",
    ),
    dict(
        question_id="ANCL-005", specialty="Ancillary",
        question_text="A patient undergoes MRI of the brain with and without contrast. CPT code?",
        option_a="70553", option_b="70551", option_c="70552", option_d="70554",
        correct_answer="A", difficulty="Medium", topic="Radiology", question_type="Conceptual",
    ),
    dict(
        question_id="ANCL-006", specialty="Ancillary",
        question_text="For outpatient therapy services under Medicare, the -GP modifier indicates:",
        option_a="Services delivered under a physical therapy plan of care", option_b="Services delivered under an occupational therapy plan of care", option_c="Services delivered under a speech therapy plan of care", option_d="Group therapy services",
        correct_answer="A", difficulty="Hard", topic="Therapy Billing", question_type="Rule-based",
    ),

    # ─── IP-DRG ───────────────────────────────────────────────────────────────
    dict(
        question_id="IPDR-001", specialty="IP-DRG",
        question_text="Which DRG base grouper logic component is the PRIMARY driver of DRG assignment for medical stays?",
        option_a="Principal diagnosis", option_b="Secondary diagnoses", option_c="Procedures performed", option_d="Patient age",
        correct_answer="A", difficulty="Easy", topic="DRG Logic", question_type="Conceptual",
    ),
    dict(
        question_id="IPDR-002", specialty="IP-DRG",
        question_text="A patient is admitted with heart failure. Which secondary diagnosis would most likely elevate the DRG from non-CC to CC?",
        option_a="Stage 3 CKD (N18.3)", option_b="Hypertension (I10)", option_c="Hyperlipidemia (E78.5)", option_d="Vitamin D deficiency (E55.9)",
        correct_answer="A", difficulty="Medium", topic="CC/MCC", question_type="Rule-based",
    ),
    dict(
        question_id="IPDR-003", specialty="IP-DRG",
        question_text="Under MS-DRG grouping, a MCC designation on a secondary diagnosis:",
        option_a="Typically results in a higher-weighted DRG than a CC designation", option_b="Has the same weight as a CC", option_c="Only applies to surgical DRGs", option_d="Applies only to principal diagnoses",
        correct_answer="A", difficulty="Medium", topic="CC/MCC", question_type="Conceptual",
    ),
    dict(
        question_id="IPDR-004", specialty="IP-DRG",
        question_text="A patient is admitted for elective knee replacement. Their BMI is 42 (morbid obesity, E66.01). What is the impact on DRG?",
        option_a="E66.01 is an MCC and will likely elevate the DRG", option_b="No impact — obesity is never a CC/MCC", option_c="Reduces length of stay expectation", option_d="Triggers a POA exempt status",
        correct_answer="A", difficulty="Hard", topic="Obesity Coding", question_type="Scenario",
    ),
    dict(
        question_id="IPDR-005", specialty="IP-DRG",
        question_text="POA (Present on Admission) indicators are required for which payer?",
        option_a="Medicare", option_b="Medicaid only", option_c="Commercial payers only", option_d="Self-pay patients",
        correct_answer="A", difficulty="Easy", topic="POA", question_type="Conceptual",
    ),
    dict(
        question_id="IPDR-006", specialty="IP-DRG",
        question_text="When a patient develops a HAC (Hospital-Acquired Condition) that was NOT present on admission, what is the Medicare payment impact?",
        option_a="Medicare may deny the higher DRG payment associated with the complication", option_b="No payment impact", option_c="Bonus payment for additional care provided", option_d="Automatic transfer to observation status",
        correct_answer="A", difficulty="Hard", topic="HAC", question_type="Rule-based",
    ),

    # ─── E&M ─────────────────────────────────────────────────────────────────
    dict(
        question_id="EMC-001", specialty="E&M",
        question_text="Under 2021 AMA E&M guidelines for office visits, which TWO components determine the level of service?",
        option_a="Medical decision making OR total time", option_b="History and physical examination", option_c="History and medical decision making", option_d="Physical examination and time",
        correct_answer="A", difficulty="Easy", topic="2021 Guidelines", question_type="Conceptual",
    ),
    dict(
        question_id="EMC-002", specialty="E&M",
        question_text="A new patient office visit with straightforward MDM is reported with which CPT code?",
        option_a="99202", option_b="99211", option_c="99201", option_d="99203",
        correct_answer="A", difficulty="Easy", topic="New Patient Codes", question_type="Conceptual",
    ),
    dict(
        question_id="EMC-003", specialty="E&M",
        question_text="A physician reviews external records and performs independent interpretation of a test already read by another physician. Under 2021 guidelines, this represents which data category?",
        option_a="Category 3 — Independent interpretation of tests", option_b="Category 1 — Tests ordered/reviewed", option_c="Category 2 — Independent historian", option_d="Category 4 — Discussion with external provider",
        correct_answer="A", difficulty="Medium", topic="MDM Data", question_type="Rule-based",
    ),
    dict(
        question_id="EMC-004", specialty="E&M",
        question_text="Telehealth office visits reported to Medicare use which place of service code (as of 2023)?",
        option_a="02 (Telehealth provided other than in patient's home) or 10 (patient's home)", option_b="11 (office)", option_c="21 (inpatient hospital)", option_d="22 (outpatient hospital)",
        correct_answer="A", difficulty="Hard", topic="Telehealth", question_type="Conceptual",
    ),
    dict(
        question_id="EMC-005", specialty="E&M",
        question_text="Which modifier is used when an E&M service is provided by the same physician on the same day as a postoperative follow-up visit covered by the global surgical package?",
        option_a="-24", option_b="-25", option_c="-57", option_d="-59",
        correct_answer="A", difficulty="Medium", topic="Global Period", question_type="Rule-based",
    ),
    dict(
        question_id="EMC-006", specialty="E&M",
        question_text="Prolonged outpatient services (99417) can be reported when the total time exceeds the maximum time for which level 5 code?",
        option_a="99215 (maximum time threshold for 99215 is 54 minutes)", option_b="99214", option_c="99213", option_d="99205",
        correct_answer="A", difficulty="Hard", topic="Prolonged Services", question_type="Rule-based",
    ),

    # ─── E&M Multispecialty ───────────────────────────────────────────────────
    dict(
        question_id="EMMS-001", specialty="E&M - Multispecialty",
        question_text="A cardiologist performs a consultation requested by the patient's primary care physician. Under Medicare, how is this reported?",
        option_a="Office/outpatient E&M code (99202-99215) — Medicare eliminated consultation codes", option_b="Inpatient consultation code (99252-99255)", option_c="Office consultation code (99241-99245)", option_d="Referral code (99243)",
        correct_answer="A", difficulty="Medium", topic="Consultations", question_type="Conceptual",
    ),
    dict(
        question_id="EMMS-002", specialty="E&M - Multispecialty",
        question_text="A surgeon performs an initial evaluation of a patient scheduled for a procedure within the global period. Which modifier is attached to the E&M?",
        option_a="-57 (decision for surgery)", option_b="-25", option_c="-24", option_d="-52",
        correct_answer="A", difficulty="Easy", topic="Surgical Modifiers", question_type="Conceptual",
    ),
    dict(
        question_id="EMMS-003", specialty="E&M - Multispecialty",
        question_text="A patient has a hospital discharge on December 31. The physician spends 40 minutes on discharge services. CPT code?",
        option_a="99239 (discharge >30 minutes)", option_b="99238 (discharge ≤30 minutes)", option_c="99232", option_d="99217",
        correct_answer="A", difficulty="Medium", topic="Hospital Discharge", question_type="Conceptual",
    ),
    dict(
        question_id="EMMS-004", specialty="E&M - Multispecialty",
        question_text="Initial nursing facility care provided on the day of admission by the admitting physician. Which code range applies?",
        option_a="99304-99306", option_b="99307-99310", option_c="99291-99292", option_d="99217-99220",
        correct_answer="A", difficulty="Medium", topic="Nursing Facility", question_type="Conceptual",
    ),
    dict(
        question_id="EMMS-005", specialty="E&M - Multispecialty",
        question_text="For subsequent hospital care visits (99231-99233), the 2021 AMA guidelines allow level selection based on:",
        option_a="MDM or total time on the floor for that calendar day", option_b="History and exam only", option_c="Exam and time only", option_d="SOAP note documentation",
        correct_answer="A", difficulty="Hard", topic="Subsequent Hospital Care", question_type="Rule-based",
    ),
    dict(
        question_id="EMMS-006", specialty="E&M - Multispecialty",
        question_text="Interprofessional telephone/internet/EHR consultations (99446-99451) require a written report sent to the requesting clinician within how many days?",
        option_a="Within the calendar day of the consultation", option_b="Within 7 business days", option_c="Within 30 days", option_d="No report required",
        correct_answer="A", difficulty="Hard", topic="Interprofessional Consults", question_type="Rule-based",
    ),

    # ─── IVR ──────────────────────────────────────────────────────────────────
    dict(
        question_id="IVR-001", specialty="IVR",
        question_text="A radiologist performs a diagnostic cerebral angiography, selective catheterization of the right internal carotid artery. Which CPT code is reported for the catheterization?",
        option_a="36217", option_b="36215", option_c="36216", option_d="36218",
        correct_answer="A", difficulty="Medium", topic="Vascular Catheterization", question_type="Conceptual",
    ),
    dict(
        question_id="IVR-002", specialty="IVR",
        question_text="Percutaneous transluminal angioplasty of a single vessel in the coronary artery is reported with:",
        option_a="92920", option_b="92924", option_c="92928", option_d="92933",
        correct_answer="A", difficulty="Easy", topic="Coronary Intervention", question_type="Conceptual",
    ),
    dict(
        question_id="IVR-003", specialty="IVR",
        question_text="Which modifier is used to indicate imaging guidance was provided using fluoroscopy during a non-vascular interventional procedure?",
        option_a="Imaging guidance is typically bundled — no modifier; separate CPT for fluoroscopy (77002)", option_b="-26", option_c="-TC", option_d="-52",
        correct_answer="A", difficulty="Hard", topic="Imaging Guidance", question_type="Rule-based",
    ),
    dict(
        question_id="IVR-004", specialty="IVR",
        question_text="A patient undergoes TACE (transarterial chemoembolization) for hepatocellular carcinoma. The procedure involves catheterization, arteriography, and embolization. How many CPT codes are typically reported?",
        option_a="Multiple codes: catheterization, imaging, and embolization codes separately", option_b="One bundled code", option_c="Two codes: catheterization and embolization", option_d="No CPT codes — covered under DRG only",
        correct_answer="A", difficulty="Hard", topic="Embolization", question_type="Scenario",
    ),
    dict(
        question_id="IVR-005", specialty="IVR",
        question_text="What CPT code is used for a non-tunneled central venous catheter placement in an adult?",
        option_a="36556", option_b="36555", option_c="36558", option_d="36560",
        correct_answer="A", difficulty="Easy", topic="Central Lines", question_type="Conceptual",
    ),
    dict(
        question_id="IVR-006", specialty="IVR",
        question_text="Percutaneous vertebroplasty for osteoporotic compression fracture of one vertebral body. CPT code?",
        option_a="22510", option_b="22511", option_c="22512", option_d="22513",
        correct_answer="A", difficulty="Medium", topic="Spinal Interventions", question_type="Conceptual",
    ),

    # ─── Anesthesia ───────────────────────────────────────────────────────────
    dict(
        question_id="ANES-001", specialty="Anesthesia",
        question_text="The formula used to calculate anesthesia payment is:",
        option_a="(Base units + Time units + Modifying units) × Conversion factor", option_b="Base units × Time units × Conversion factor", option_c="(Base units + Time units) ÷ Conversion factor", option_d="Base units × Conversion factor only",
        correct_answer="A", difficulty="Easy", topic="Payment Formula", question_type="Conceptual",
    ),
    dict(
        question_id="ANES-002", specialty="Anesthesia",
        question_text="Anesthesia for a total hip arthroplasty is reported with which base code?",
        option_a="01402", option_b="01400", option_c="01404", option_d="01380",
        correct_answer="A", difficulty="Medium", topic="Orthopedic Anesthesia", question_type="Conceptual",
    ),
    dict(
        question_id="ANES-003", specialty="Anesthesia",
        question_text="Modifier -QZ indicates anesthesia was provided by:",
        option_a="CRNA without medical direction by a physician", option_b="CRNA with medical direction", option_c="Anesthesiologist performing the anesthesia personally", option_d="Resident supervised by an attending anesthesiologist",
        correct_answer="A", difficulty="Medium", topic="Anesthesia Modifiers", question_type="Conceptual",
    ),
    dict(
        question_id="ANES-004", specialty="Anesthesia",
        question_text="A patient is classified as ASA physical status 4 (severe systemic disease, constant threat to life). What qualifying circumstance modifier might be added?",
        option_a="P4 physical status modifier (P4)", option_b="P5 modifier", option_c="-47 (anesthesia by surgeon)", option_d="No modifier; ASA status is not separately reported",
        correct_answer="A", difficulty="Hard", topic="ASA Status", question_type="Rule-based",
    ),
    dict(
        question_id="ANES-005", specialty="Anesthesia",
        question_text="One time unit in anesthesia billing typically equals:",
        option_a="15 minutes", option_b="10 minutes", option_c="30 minutes", option_d="1 hour",
        correct_answer="A", difficulty="Easy", topic="Time Units", question_type="Conceptual",
    ),
    dict(
        question_id="ANES-006", specialty="Anesthesia",
        question_text="Emergency anesthesia is indicated by qualifying circumstance code:",
        option_a="99140", option_b="99100", option_c="99135", option_d="99116",
        correct_answer="A", difficulty="Medium", topic="Qualifying Circumstances", question_type="Conceptual",
    ),
]


def seed_sample_questions(db: Session) -> None:
    """Insert seed questions. Skips any that already exist by question_id."""
    for q_data in SEED_QUESTIONS:
        existing = db.query(AssessmentQuestion).filter(
            AssessmentQuestion.question_id == q_data["question_id"]
        ).first()
        if existing:
            continue
        q = AssessmentQuestion(
            question_id=q_data["question_id"],
            specialty=q_data["specialty"],
            question_text=q_data["question_text"],
            option_a=q_data["option_a"],
            option_b=q_data["option_b"],
            option_c=q_data["option_c"],
            option_d=q_data["option_d"],
            correct_answer=q_data["correct_answer"],
            difficulty=q_data["difficulty"],
            topic=q_data.get("topic"),
            question_type=q_data.get("question_type", "Conceptual"),
            status="Active",
            uploaded_by="system",
        )
        db.add(q)
    db.commit()
