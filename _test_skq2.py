import comtypes.client
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

# Find stock-related structs
stock_structs = [x for x in dir(sk) if 'Stock' in x or 'stock' in x]
print("Stock-related:", stock_structs[:20])

# Find SKQuote related
quote_items = [x for x in dir(sk) if 'Quote' in x or 'quote' in x]
print("\nQuote-related:", quote_items[:20])

# Check ISKQuoteLib methods
methods = [x for x in dir(sk.ISKQuoteLib) if 'Get' in x or 'get' in x]
print("\nISKQuoteLib Get methods:", methods[:20])
