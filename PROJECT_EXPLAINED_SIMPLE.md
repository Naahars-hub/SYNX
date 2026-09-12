# 🛒 The "Explain It Like I'm 5" Guide to SYNX
### Legal Metrology Compliance Checker (SIH 2026 — Problem #26034)

---

## 🧐 What is this project in ONE sentence?
> **It is an AI-powered digital police officer that looks at packaging (like chips, juice bottles, or biscuit packets) and catches brands if they try to trick you or break Indian packaging laws.**

---

## 🍕 The Real-Life Problem (Why does this even exist?)

Imagine you walk into a grocery store and pick up a bottle of mango juice or a packet of chips:
1. **You look for the price**: But the price is hidden in tiny, microscopic, unreadable text on the plastic cap.
2. **You look for the weight**: It says "200 gms" instead of the legal "200 g", or the bag is 80% air and doesn't clearly say how much food is actually inside.
3. **Something tastes weird**: You look for the customer care phone number, but it's nowhere to be found, or it's just a fake line.
4. **Who made this?**: There's no factory address or 6-digit PIN code to find the manufacturer.

### 🏛️ The Law: Legal Metrology (Packaged Commodities) Rules, 2011
In India, the government has strict consumer protection laws. Every single packaged product **MUST** print 8 specific things clearly. If a company fails to do so, they face heavy fines (up to ₹1,00,000) or even jail time under Section 36(1) of the Legal Metrology Act, 2009.

### 🤦‍♂️ The Old Way (How it was done before):
Government inspectors had to walk into stores with a **physical ruler, a magnifying glass, and a notepad**, manually measuring letters and writing down violations by hand.
- It took 20 to 30 minutes per product.
- Humans make mistakes or miss things.
- It is impossible to manually check millions of products sold across India.

---

## 🚀 The SYNX Solution (What WE Built)

We built an **automated scanner**:
1. You snap 2 or 3 photos of any product using your smartphone (Front, Back, and the Cap/Flap).
2. Tap **"Send to Laptop"**.
3. In **3 seconds**, our software:
   - Reads every single word, number, and stamp on the packaging.
   - Measures letter heights down to the exact **millimeter**.
   - Checks all Indian statutory rules automatically.
   - Gives a color-coded scorecard (**PASS / FAIL**).
   - Generates an **official, legally valid PDF court certificate** with fine calculations!

---

## 🔍 The 8 Rules We Check (Explained Simply)

| What the Law Says | What It Means in Plain English | What We Catch |
|---|---|---|
| **1. Commodity Name** | *"What is inside this bag?"* | Brands can't just write vague marketing words like *"Thermally Processed Deliciousness"*. They must clearly state: *"Ready to Serve Fruit Drink"*. |
| **2. Net Quantity** | *"How much stuff am I getting?"* | Must declare weight/volume in legal metric units (`400 ml` or `250 g`). No illegal symbols like `gms`, `kgs`, or `ltrs`. Also catches if brands try to pass off "Serving Size: 50g" as the total pack weight! |
| **3. Maximum Retail Price (MRP)** | *"What does it cost?"* | Must clearly state the total price (e.g. `Rs. 30.00`) and declare that it is *"inclusive of all taxes"*. |
| **4. Unit Sale Price (USP)** | *"Is this actually a good deal?"* | Must show the price per single unit (e.g. `Rs. 0.075 / ml`). This lets consumers compare if the big bottle is actually cheaper than two small bottles. |
| **5. Manufacturing Date** | *"When was this made?"* | Must state the month and year of manufacture (e.g. `12/2026`). Catches faint, dot-matrix inkjet stamps printed on bottle necks or bag folds. |
| **6. Manufacturer Address** | *"Who made this and where?"* | Must state the company name, complete address, and a valid **6-digit Indian PIN code** (e.g. `462046`). |
| **7. Customer Care** | *"Who do I call if there's a bug in my food?"* | Must provide a real telephone helpline or email address. We also make sure the brand didn't just paste an FSSAI food license number to pretend it's a phone number! |
| **8. Country of Origin** | *"Where on Earth was it made?"* | Must declare where it came from (e.g. *"Made in India"*). |
| **Rule 7: Font Size Rule** | *"Can human eyes actually read it?"* | The law calculates the size of the front label (PDP) and says: *"If your package is this big, your text MUST be at least 2.0mm or 4.0mm tall!"* Our software mathematically measures the real-world height of the letters! |

---

## 💡 Cool Tricks Our Software Does (Why it's not just basic OCR)

1. **📱 Phone-to-Laptop Zero-Install Sync**:
   - Inspectors don't need to install any mobile app.
   - Just click "Connect Phone Camera" on the laptop, scan the QR code with your phone camera, snap photos, and boom — they show up on the laptop screen instantly!
2. **🔄 Multi-Angle Packaging Sticher**:
   - Real products are 3D! On a juice bottle: the brand is on the front, ingredients are on the back, and the price/date is stamped on the cap.
   - Our system lets you upload all sides and combines them into one single brain.
3. **🕶️ Anti-Glare & Shiny Foil Handling**:
   - Potato chip packets and shiny plastic bottles reflect light like mirrors.
   - We use computer vision filters (CLAHE) to cut through glare and read faint dot-matrix printer stamps.
4. **🥗 Nutrition Table Blacklist**:
   - Packages have nutrition facts (Sugar: 14g, Fat: 0g, Energy: 100kJ).
   - Dumb OCR engines confuse "Sugar: 14g" as the product weight or "100 kJ" as the price.
   - Our engine knows the difference between a nutrition table and mandatory legal declarations!
5. **📏 Real Millimeter Measurement on a Flat Screen**:
   - A screen only sees pixels, not millimeters.
   - By entering the package size (e.g., 120mm wide) or placing a ₹5 coin next to it, our software calculates the exact real-world millimeter scale!

---

## 🏃 How to Run This (Literally 1 Click)

1. Find the file named **`start.bat`** in this folder.
2. **Double-click it.**
3. Your web browser will pop open to `http://127.0.0.1:8000`.
4. Click on any of the pre-loaded sample products (or upload your own photos).
5. Watch the AI instantly scan, highlight text in green/red boxes, and let you download the official PDF audit report!

---

*Made with ❤️ by Team SYNX for Smart India Hackathon 2026*
