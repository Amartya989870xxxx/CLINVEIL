"""Vocabularies used as *evidence* by the detectors.

Provenance: every list here was written by the CLINVEIL team from general
knowledge of Indian naming conventions, Hindi/Hinglish usage, clinical
terminology and public administrative geography (Uttar Pradesh districts).
Nothing is extracted from the organiser's practice data or answer key. The name
gazetteer is deliberately broad (common pan-Indian given names and surnames) and
is never sufficient on its own to redact a token. Detectors combine it with
context (labels, honorifics, relationship markers, structure).
"""

from __future__ import annotations


def _words(s: str) -> frozenset[str]:
    return frozenset(w.strip().casefold() for w in s.split() if w.strip())


# --------------------------------------------------------------------------- person cues
#: Honorifics that follow a patient's name in Hinglish ("Shahid sahab ka BP …").
PATIENT_HONORIFICS = _words("ji jee sahab sahib saheb saab didi behenji behen bahenji babu amma madam memsaab")
#: Kinship terms used as forms of address; the named person is a relative/attendant.
KINSHIP_TERMS = _words(
    "mama mami chacha chachu chachi papa pappa mummy mumma maa bhaiya bhaiyya bhai bhabhi bhabi beta beti dada "
    "dadi nana nani bua mausi mausa fufa phupha tau tai jija jiju uncle aunty auntie bhanja bhatija devar nanad "
    "sasur saas"
)
#: Prefix titles before a name.
PREFIX_TITLES = _words("mr mrs ms miss shri shree sri smt shrimati kumari km master baby late sushri")
DEVA_PREFIX_TITLES = frozenset({"श्री", "श्रीमती", "सुश्री", "कुमारी", "स्व", "स्व."})
DEVA_HONORIFICS = frozenset({"जी", "साहब", "दीदी", "बाबू", "अम्मा", "बहनजी"})
#: Tokens that are part of names but identify nobody on their own (never propagated alone).
GENERIC_NAME_TOKENS = _words(
    "devi kumar kumari singh kaur bai lal ram prasad chand md mohd mohammad muhammad mohammed sk shaikh syed "
    "begum bano khatoon bibi ben bhai ji kunwar rani raja nath das"
) | frozenset({"देवी", "कुमार", "कुमारी", "सिंह", "कौर", "बाई", "लाल", "मोहम्मद", "बानो", "बेगम", "ख़ातून", "खातून"})
#: Words that look like capitalised names in clinical prose but are not people.
NOT_NAME_WORDS = _words(
    "patient pt patients doctor dr doctors nurse sister staff ward bed room opd ipd icu emergency casualty hospital "
    "clinic lab labs laboratory pathology diagnostics report reports sample test tests result results date time "
    "name age sex male female yrs years year months days weeks mob mobile phone contact address tehsil distt "
    "district village vill gram mohalla near opp behind house makan ward road street nagar colony basti sector "
    "advice adv review follow up rx diagnosis history course medications medicines discharge admission summary "
    "complaints complaint presenting investigations impression plan remarks note notes nursing forwarded attachment "
    "morning evening night today yesterday tomorrow next previous normal stable fever cough cold pain headache "
    "vomiting diarrhoea weakness tablet tab capsule cap inj injection syrup syp drops ointment dose daily "
    "consultant surgeon physician medicine surgery pulmonology cardiology paediatrics orthopaedics gynaecology "
    "general internal referral referred visitor visitors log round rounds evening attendant relative guardian "
    "the a an and or of to in on at by for with from is was are were be been this that these those it he she they "
    "his her their your our my me we you i not no yes ok okay please thanks thank regards sir madam team "
    "monday tuesday wednesday thursday friday saturday sunday january february march april may june july august "
    "september october november december jan feb mar apr jun jul aug sep sept oct nov dec "
    "india uttar pradesh up lucknow kanpur delhi anganwadi worker workers ambulance trip remarks oxygen "
    "given route called stable condition hai ka ki ke ko ne se aur nahi bhi ab abhi kal aaj "
    "positive negative reactive nonreactive hb rbs fbs bp pulse spo2 temp ecg mri ct usg xray cbc lft kft "
    "dm htn tb att ckd copd ihd cad bd od tds sos hs stat qid bid tid prn"
)

# --------------------------------------------------------------------------- relationship markers
#: Latin relationship markers followed by a relative's name.
#: ``H/O`` is deliberately absent: clinically it means "history of" (a meaning trap).
RELATION_MARKERS = (
    "s/o",
    "d/o",
    "w/o",
    "f/o",
    "m/o",
    "c/o",
    "son of",
    "daughter of",
    "wife of",
    "husband of",
    "father of",
    "mother of",
    "care of",
)
#: Devanagari relationship words (after the patient's name or as labels).
DEVA_RELATION_WORDS = frozenset(
    {"पुत्र", "पुत्री", "पत्नी", "पति", "पिता", "माता", "बेटा", "बेटी", "सुपुत्र", "सुपुत्री", "धर्मपत्नी"}
)

# --------------------------------------------------------------------------- clinical vocabulary
#: Presenting-complaint words: "C/O <one of these>" is a complaint, not "care of".
COMPLAINT_WORDS = _words(
    "fever bukhar pain cough cold headache giddiness dizziness vomiting nausea loose stools diarrhoea diarrhea "
    "constipation burning micturition breathlessness sob dyspnoea dyspnea chest abdominal abdomen weakness fatigue "
    "generalised generalized swelling oedema edema rash itching bleeding palpitations syncope fits seizure "
    "convulsions jaundice yellowish weight loss appetite body ache aches joint back knee throat sore ear eye "
    "redness discharge burning urinary frequent bodyache chills rigors sweating anxiety insomnia cramps numbness "
    "tingling blurring vision hematuria haematuria dysuria fainting low high blood pressure sugar khansi dard "
    "ulti dast chakkar kamzori sujan saans"
)
DRUG_WORDS = _words(
    "paracetamol dolo crocin calpol pcm ibuprofen brufen diclofenac aceclofenac nimesulide aspirin ecosprin "
    "amoxicillin augmentin azithromycin azee ciprofloxacin ofloxacin levofloxacin doxycycline cefixime "
    "ceftriaxone cefuroxime metronidazole tinidazole norfloxacin nitrofurantoin metformin glimepiride gliclazide "
    "sitagliptin vildagliptin insulin glargine amlodipine telmisartan losartan ramipril enalapril atenolol "
    "metoprolol propranolol hydrochlorothiazide chlorthalidone furosemide lasix spironolactone atorvastatin "
    "rosuvastatin clopidogrel warfarin heparin levothyroxine thyroxine eltroxin pantoprazole pan omeprazole "
    "rabeprazole esomeprazole ranitidine domperidone ondansetron emeset cetirizine levocetirizine montelukast "
    "salbutamol asthalin budesonide formoterol prednisolone dexamethasone hydrocortisone iron folic ferrous "
    "calcium vitamin multivitamin zinc ors albendazole ivermectin artesunate chloroquine primaquine rifampicin "
    "isoniazid pyrazinamide ethambutol oseltamivir acyclovir fluconazole clotrimazole mupirocin betadine "
    "ringer saline dextrose ns rl tramadol morphine diazepam alprazolam clonazepam phenytoin levetiracetam "
    "sodium valproate carbamazepine haloperidol olanzapine sertraline escitalopram amitriptyline "
    "inhaler nebulisation nebulization tab cap inj syp inh oint"
)
DISEASE_WORDS = _words(
    "diabetes mellitus hypertension tuberculosis typhoid dengue malaria chikungunya pneumonia bronchitis asthma "
    "copd anaemia anemia jaundice hepatitis cirrhosis gastritis gastroenteritis appendicitis cholecystitis "
    "pancreatitis nephritis nephrotic ckd uti sepsis cellulitis abscess fracture arthritis osteoarthritis "
    "hypothyroidism hyperthyroidism stroke epilepsy migraine depression psychosis schizophrenia cataract "
    "glaucoma otitis tonsillitis sinusitis covid influenza measles mumps chickenpox leprosy filariasis "
    "kala azar cancer carcinoma tumour tumor lymphoma leukaemia leukemia disease syndrome disorder infection "
    "deficiency failure injury bite snake dog scorpion poisoning burns pregnancy anc pih eclampsia"
)
#: Words that, followed by "'s", form a disease eponym rather than a possessive person name.
EPONYM_HEADS = _words(
    "disease syndrome palsy sign test phenomenon ulcer sarcoma lymphoma anaemia anemia "
    "triad law reflex manoeuvre maneuver fracture contracture cyst node"
)
CLINICAL_ABBREVIATIONS = frozenset(
    "OPD IPD ICU NICU PICU CCU HDU ER OT ECG EKG EEG CT MRI USG CXR CBC LFT KFT RFT TSH HbA1c RBS FBS PPBS BP "
    "SpO2 HR RR GCS DM DM2 HTN TB ATT CKD COPD IHD CAD CVA UTI ARDS AKI MI CHF ICD LOINC IV IM SC PO SOS STAT "
    "OD BD TDS QID HS PRN AC PC NS RL ORS ANC PNC ASHA ANM PHC CHC AIIMS PMJAY ABHA ABDM HIV HBsAg HCV VDRL".split()
)

# --------------------------------------------------------------------------- places
#: Uttar Pradesh districts (public administrative areas; kept, never redacted).
UP_DISTRICTS = _words(
    "agra aligarh ambedkarnagar amethi amroha auraiya ayodhya azamgarh baghpat bahraich ballia balrampur banda "
    "barabanki bareilly basti bhadohi bijnor budaun bulandshahr chandauli chitrakoot deoria etah etawah "
    "farrukhabad fatehpur firozabad gautam buddha nagar ghaziabad ghazipur gonda gorakhpur hamirpur hapur hardoi "
    "hathras jalaun jaunpur jhansi kannauj kanpur dehat nagar kasganj kaushambi kushinagar lakhimpur kheri "
    "lalitpur lucknow maharajganj mahoba mainpuri mathura mau meerut mirzapur moradabad muzaffarnagar pilibhit "
    "pratapgarh prayagraj allahabad rae bareli raebareli rampur saharanpur sambhal sant kabir shahjahanpur "
    "shamli shravasti siddharthnagar sitapur sonbhadra sultanpur unnao varanasi"
)
LOCATION_LABEL_WORDS = _words("tehsil tahsil taluk taluka block distt dist district jila zila state pradesh")

# --------------------------------------------------------------------------- name gazetteer
#: Common Indian given names (pan-Indian, Hindu/Muslim/Sikh/Christian), Latin spellings.
#: Both name lists were de-duplicated against the organiser's practice answer key: every token that
#: occurs as a practice patient/relative/canary or doctor name was REMOVED, so practice-data measurements cannot
#: benefit from the gazetteer (see docs/evaluation/PHASE2_DETECTION.md, "Lexicon provenance").
GIVEN_NAMES = _words(
    "aarav aarti abdul abhay abhishek aditi aditya afroz ahmad aisha ajit akash akbar akhil alka alok aman "
    "amar amarjeet amina amir amit amita amrita anand anjali anju ankit ankita anuj anupam anuradha anwar "
    "arun aruna arvind ashish asif asma azhar babita balbir balwant bharat bhavna bhupendra bimla chandan "
    "chandni chetan deepa deepika dev devendra dharmendra dhruv dilip divya durga farah farhan faisal feroz "
    "ganesh gaurav girish gopal govind gulshan gurpreet gurmeet hamid hari hemant hemlata hina imran indu "
    "ishaan jagjit jai jameel jasbir jaya jitendra jyoti kailash kajal kalpana kanchan karan khalid kiran "
    "kishore krishna kusum lakshmi lalit lata laxmi madhu mahendra manish manju mansi meena meera mohini "
    "monika munni nadeem naeem nafisa nagendra narendra naveen neelam neeraj nikhil nirmala nisha nitin noor "
    "pankaj pawan pooja poonam prabhu pradeep pramod prashant preeti prem priya priyanka puja pushpa rachna "
    "raj rajesh rajendra rajeev rajni rakesh ram rani ranjit ravi rekha renu ritu rohit roshan ruby sachin "
    "sadhana sagar sajid sandeep sangeeta sanjay sanjeev santosh sapna satish savita seema shakeel shalini "
    "sharda shashi sheela shilpa shiv shobha simran sita sonia sudha sudhir sumit surinder sushila swati "
    "tabassum tanvir tarun tasleem uma varun vikram vinay vinod vipin vishal yash yogesh zakir"
)
SURNAMES = _words(
    "agarwal ahmad ali arora bajpai banerjee bansal bhatt bhatia bose chandra chaturvedi chopra das dubey "
    "dwivedi gill goel jain jaiswal joshi kapoor kashyap khan khanna kushwaha maurya mehra mehta nair pal "
    "pandit pathak prajapati rathore rao rawat saxena shah shukla sinha tripathi trivedi upadhyay vaishya "
    "varma begum"
)
