import pathlib
p = pathlib.Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\test_smart_order.py")
c = p.read_text("utf-8")

old = """    m_pSKOrder.SKOrderLib_Initialize()
    print("Order system ready.")"""

new = """    # Generate trading key (required for order placement)
    nCode = m_pSKCenter.SKCenterLib_GenerateKeyCert(CUST_ID, CUST_ID)
    msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
    print(f"GenerateKeyCert: {msg}")

    m_pSKOrder.SKOrderLib_Initialize()

    # Read certificate for trading
    nCode = m_pSKOrder.ReadCertByID(CUST_ID)
    msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
    print(f"ReadCertByID: {msg}")

    print("Order system ready.")"""

c = c.replace(old, new)
p.write_text(c, "utf-8")
print("fixed")
