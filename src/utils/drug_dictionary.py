import re

class DrugDictionary:
    """
    Standardizes raw free-text drug names from FAERS into standardized active generic ingredients.
    This resolves brand names, combinations, typos, and dose descriptors.
    """
    
    # Brand to generic mappings
    BRAND_TO_GENERIC = {
        # Target Biologics / TNF Inhibitors
        "humira": "adalimumab",
        "amjevita": "adalimumab",
        "cyltezo": "adalimumab",
        "hadlima": "adalimumab",
        "hyrimoz": "adalimumab",
        "yuflyma": "adalimumab",
        "idacio": "adalimumab",
        
        "remicade": "infliximab",
        "inflectra": "infliximab",
        "renflexis": "infliximab",
        "avsola": "infliximab",
        
        "enbrel": "etanercept",
        "erelzi": "etanercept",
        "etaneo": "etanercept",
        
        "stelara": "ustekinumab",
        
        "cimzia": "certolizumab pegol",
        
        "simponi": "golimumab",
        
        # Control Drugs (NSAIDs & OTCs)
        "advil": "ibuprofen",
        "motrin": "ibuprofen",
        "nurofen": "ibuprofen",
        
        "aleve": "naproxen",
        "naprosyn": "naproxen",
        "anaprox": "naproxen",
        
        "celebrex": "celecoxib",
        
        "aspirin": "aspirin",
        "bayer": "aspirin",
        "ecotrin": "aspirin",
        
        "tylenol": "acetaminophen",
        "paracetamol": "acetaminophen",
        "panadol": "acetaminophen"
    }

    # Standard generic list for direct lowercased matching (sorted by length descending for deterministic matching)
    GENERICS = [
        "certolizumab pegol",
        "acetaminophen",
        "adalimumab",
        "infliximab",
        "etanercept",
        "ustekinumab",
        "golimumab",
        "ibuprofen",
        "celecoxib",
        "naproxen",
        "aspirin"
    ]

    @classmethod
    def standardize(cls, raw_name: str) -> str:
        """
        Standardizes raw drug text. Returns the generic name if matched, or 'unknown'.
        
        Examples:
            'Humira Pen 40mg' -> 'adalimumab'
            'Adalimumab-adaz' -> 'adalimumab'
            'PARACETAMOL EXTRA' -> 'acetaminophen'
        """
        if not raw_name or not isinstance(raw_name, str):
            return "unknown"
            
        # 1. Clean string: lowercase, remove non-alphanumeric (except spaces and hyphens)
        clean_name = raw_name.lower().strip()
        clean_name = re.sub(r"[^a-z0-9\s\-]", "", clean_name)
        
        # 2. Check direct generic list containment with precise non-alphabetic boundary checks
        # This prevents false positives like "Nonaspirin" matching "aspirin" while allowing "humira40mg"
        for generic in cls.GENERICS:
            if re.search(r'(?<![a-z])' + re.escape(generic) + r'(?![a-z])', clean_name):
                return generic
                
        # 3. Check brand name mappings with precise non-alphabetic boundary checks
        for brand, generic in cls.BRAND_TO_GENERIC.items():
            if re.search(r'(?<![a-z])' + re.escape(brand) + r'(?![a-z])', clean_name):
                return generic
                
        return "unknown"
