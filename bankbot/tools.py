"""Three read-only tools. Model-supplied names never execute arbitrary code."""
import json
from .dialogue import PRODUCT_ALIASES
from .language import canonical_city
from .catalog import SERVICES, service_action
from .forms import clean_prefill
from .student_finance import search_funding
from .scenarios import transfer_quote
from .intent import permitted


def schema(name, description, field):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": {field: {"type": "string"}},
                           "required": [field], "additionalProperties": False}}}


TOOL_SCHEMAS = [
    schema("search_bank_faq", "Search fictional CampusBank policies and procedures. Include the product and the specific question. Use for bank-specific facts before answering.", "query"),
    schema("get_product_info", "Get the authoritative fictional product record, including fees, required documents, eligibility and interest. Product names: student_account, everyday_account, savings_account, debit_card, credit_card, personal_loan.", "product_name"),
    schema("find_branch", "Find fictional branch addresses and opening hours in a named city. Ask for the city if it is missing. This tool only reads local demo records.", "city"),
]
window_schema=schema("open_service_window", "Prepare a local service window after explaining how the user can apply online, request a card, report a lost card, transfer, open savings, apply for a loan, book a branch or contact human support. This ONLY creates a clickable UI entry, never submits an application or moves money. Choose one approved service ID.", "service_id")
window_schema["function"]["parameters"]["properties"]["service_id"]["enum"]=list(SERVICES)
window_schema['function']['description'] += ' Include prefill with explicitly supplied demo form fields, preserving earlier fields when a customer changes one item. Never ask for IBAN, account numbers, PINs or actual payment credentials. Opening does not submit.'
window_schema['function']['parameters']['properties']['prefill'] = {
    'type':'object','description':'Partial form values explicitly supplied by the customer. Omit consent checkboxes. Use the catalog fields supplied in system context.',
    'properties':{f['name']:{'type':['string','number','boolean']} for s in SERVICES.values() for f in s['fields']},
    'additionalProperties':False}
TOOL_SCHEMAS.append(window_schema)
TOOL_SCHEMAS.append(schema('search_student_funding','Look up fictional student loans, scholarships and grants. These are demo records, never real university or government policy. Return eligibility guidance, documents and next steps.','query'))
TOOL_SCHEMAS.append({'type':'function','function':{'name':'get_transfer_quote','description':'Calculate the same fictional GBP fee/FX estimate as the transfer window. Use before giving transfer totals or recipient amounts. Domestic GBP; international EUR/USD supported. Never a real exchange quote.','parameters':{'type':'object','properties':{'amount':{'type':'string'},'transfer_type':{'type':'string','enum':['domestic','international']},'currency':{'type':'string','enum':['GBP','EUR','USD']}},'required':['amount','transfer_type'],'additionalProperties':False}}})


class Tools:
    def __init__(self, knowledge, retriever, threshold=0.18):
        self.knowledge = knowledge
        self.retriever = retriever
        self.threshold = threshold

    def execute(self, name: str, arguments: str | dict,constraints=None) -> dict:
        required = {"search_bank_faq": "query", "get_product_info": "product_name", "find_branch": "city", "open_service_window":"service_id",'search_student_funding':'query','get_transfer_quote':'amount'}
        if not isinstance(name, str) or name not in required:
            return {"error": "unknown_tool", "message": "This tool is not available."}
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (ValueError, TypeError):
            return {"error": "invalid_arguments", "message": "Arguments must be a JSON object."}
        if name=='get_transfer_quote':
            if not isinstance(args,dict) or set(args)-{'amount','transfer_type','currency'} or not all(isinstance(v,str) for v in args.values()) or not {'amount','transfer_type'}<=set(args):return {'error':'invalid_arguments','message':'Supply an amount, transfer_type and optional supported currency.'}
            try:return {'quote':transfer_quote(args['amount'],args['transfer_type'],currency=args.get('currency')),'source_ids':['DEMO_TRANSFER_QUOTE'],'fictional':True}
            except ValueError as exc:return {'error':'invalid_arguments','message':str(exc)}
        field = required[name]
        allowed={field,'prefill'} if name=='open_service_window' else {field}
        if not isinstance(args, dict) or set(args)-allowed or field not in args or not isinstance(args.get(field), str) or not args[field].strip() or len(args[field]) > 2000:
            return {"error": "invalid_arguments", "message": f"Supply only a non-empty string field named {field}."}
        value = args[field].strip()
        if name=='search_student_funding':
            records=search_funding(value,exclude_loan=(constraints or {}).get('exclude_loan',False))
            return {'records':records,'source_ids':[r['id'] for r in records],'found':bool(records),'fictional':True}
        if name == "open_service_window":
            if not permitted(value,constraints):return {'error':'excluded_by_user','message':'The user excluded loans. Offer funding_enquiry with a single funding_type selection instead.'}
            action=service_action(value)
            if action:
                try:action['prefill']=clean_prefill(value,args.get('prefill',{}))
                except ValueError as exc:return {'error':'invalid_arguments','message':str(exc)}
            return {"ui_action":action,"prepared":True,"message":"A clickable demo service window is ready. The user must open it and confirm any submission."} if action else {"error":"unknown_service","message":"Choose an approved local service window."}
        if name == "search_bank_faq":
            hits = self.retriever.search(value,exclude_loan=(constraints or {}).get('exclude_loan',False))
            hits = [h for h in hits if h["score"] >= self.threshold]
            return {"records": hits, "source_ids": [h["faq_id"] for h in hits], "found": bool(hits)}
        if name == "get_product_info":
            canonical = value.lower().replace(" ", "_")
            for product, aliases in PRODUCT_ALIASES.items():
                if value.lower() in aliases:
                    canonical = product
            result = next((p for p in self.knowledge.products if p["product_name"] == canonical), None)
            return {"record": result, "found": result is not None,
                    "source_ids": [result["source_id"]] if result else []}
        value = canonical_city(value)
        results = [b for b in self.knowledge.branches if b["city"].casefold() == value.casefold()]
        return {"records": results, "found": bool(results), "source_ids": [b["branch_id"] for b in results]}
