# Google Play Store Complete Registration & Publishing Guide
### SmartVision: DigiCampus Idea Lab (in.ac.jietjodhpur.smartvision)

यह गाइड आपको अपनी वेबसाइट/सिस्टम को **Google Play Store** पर आधिकारिक रूप से पब्लिश करने के हर एक स्टेप को हिंदी और इंग्लिश में विस्तार से समझाती है।

---

## 📋 पूर्व-तैयारी (Everything is Already Prepared for You!)

हमने आपके लिए निम्नलिखित सभी चीजें तैयार कर दी हैं:
1. **Android Studio Native App Project**: `android/` फोल्डर में पूरा Gradle प्रोजेक्ट मौजूद है।
2. **App Icons (All Densities)**: `android/app/src/main/res/mipmap-*/` और `play_store/assets/app_icon_512.png` (512x512)।
3. **Feature Graphic Banner**: `play_store/assets/feature_graphic_1024x500.png` (1024x500)।
4. **Play Store Description & Metadata**: `play_store/STORE_LISTING.md`।
5. **Data Safety Questionnaire Responses**: `play_store/DATA_SAFETY_SPEC.md`।
6. **Privacy Policy Link**: `https://idea-lab-project-69.vercel.app/privacy`।

---

## 🚀 Step 1: Google Play Console अकाउंट सेटअप

1. ब्राउज़र में **[https://play.google.com/console/signup](https://play.google.com/console/signup)** पर जाएं।
2. अपने गूगल अकाउंट (जैसे `aditya6969jain@gmail.com`) से साइन-इन करें।
3. **Developer Account Type** चुनें:
   - **Individual** (व्यक्तिगत डेवलपर) चुनें।
4. गूगल प्ले कंसोल की एकमुश्त (One-time) फीस **$25 USD** (लगभग ₹2,100) अपने इंटरनेशनल क्रेडिट/डेबिट कार्ड से भरें।
5. अपना सरकारी पहचान पत्र (PAN Card / Aadhaar / Passport / Voter ID) अपलोड करके **Identity Verification** पूरा करें (आमतौर पर 1-2 घंटे में वेरीफाई हो जाता है)।

---

## 🔨 Step 2: Signed Android App Bundle (.aab) जनरेट करना

Google Play Store पर नई ऐप्स के लिए `.apk` की जगह **`.aab` (Android App Bundle)** अनिवार्य है।

### तरीका A (Android Studio द्वारा - 2 मिनट):
1. अपने लैपटॉप में **Android Studio** खोलें।
2. **Open** पर क्लिक करें और अपने प्रोजेक्ट का `android` फोल्डर चुनें:
   `c:\Users\ADITYA JAIN\Downloads\IDEA LAB PROJECT 69(^-^)\android`
3. Gradle सिंक पूरा होने दें।
4. टॉप मेनू में जाएं: **Build** > **Generate Signed Bundle / APK...**
5. **Android App Bundle** चुनें और **Next** पर क्लिक करें।
6. **Keystore Path**:
   - यदि पहली बार बना रहे हैं, तो **Create new...** पर क्लिक करें।
   - की-स्टोर पाथ चुनें (जैसे `smartvision-release.jks`), पासवर्ड सेट करें (उदा. `SmartVision@2026`), और First & Last Name में `Aditya Jain` लिखें।
7. **Destination Folder**: रिलीज फोल्डर चुनें।
8. **Build Variant**: **`release`** चुनें और **Finish** दबाएं।
9. 1 मिनट में आपकी **`app-release.aab`** फाइल बनकर तैयार हो जाएगी!

---

## 📝 Step 3: Google Play Console में ऐप रजिस्टर करना

1. [Google Play Console](https://play.google.com/console) डैशबोर्ड पर जाएं।
2. ऊपर दाईं ओर **"Create app"** बटन पर क्लिक करें।
3. निम्नलिखित विवरण भरें:
   - **App name**: `SmartVision: DigiCampus Idea Lab`
   - **Default language**: `English (United States) - en-US` या `English (India)`
   - **App or game**: `App`
   - **Free or paid**: `Free`
4. नीचे दी गई दोनों Declarations (Developer Program Policies और US Export Laws) पर टिक करें और **"Create app"** पर क्लिक करें।

---

## ⚙️ Step 4: App Setup पूरा करना (10-Minute Checklist)

डैशबोर्ड पर बाईं तरफ **"Set up your app"** सेक्शन में जाएं:

1. **Privacy policy**:
   - URL डालें: `https://idea-lab-project-69.vercel.app/privacy`
2. **App access**:
   - चुनें: *"All or some functionality in my app is restricted"*
   - **Add credentials** पर क्लिक करें:
     - Name: `Student Test Account`
     - Username: `aditya.26ai3482@jietjodhpur.ac.in`
     - Password: `Aditya69`
     - Instructions: *"Official JIET student test login for reviewing attendance ledger"*
3. **Ads**:
   - चुनें: *"No, my app does not contain ads"*
4. **Content rating**:
   - प्रश्नावली शुरू करें।
   - ईमेल डालें: `aditya6969jain@gmail.com`
   - Category: `Utility, Productivity, Communication or Other`
   - सभी सवालों में **No** चुनें (कोई हिंसक या वयस्क सामग्री नहीं है)।
   - आपकी रेटिंग **Everyone / PEGI 3** आ जाएगी।
5. **Target audience**:
   - टारगेट आयु: **18 and over** (कॉलेज छात्र)।
6. **Data safety** (अत्यंत महत्वपूर्ण):
   - `play_store/DATA_SAFETY_SPEC.md` फाइल खोलें।
   - उसमें दिए गए हूबहू उत्तर (Encrypted in transit: Yes, Deletion request: Yes, Personal Info & Biometric data) भरें।
7. **Government apps**:
   - चुनें: *"No, this app is not an official government app"*.
8. **Financial features**:
   - चुनें: *"My app doesn't provide any financial features"*.

---

## 🎨 Step 5: Store Listing (ग्राफिक्स और विवरण)

बाईं तरफ मेनू में **Grow > Store presence > Main store listing** पर जाएं:

1. **Short description** (कॉपी करें):
   ```
   AI face recognition attendance & DigiCampus academic portal for Idea Lab JIET.
   ```
2. **Full description**:
   - `play_store/STORE_LISTING.md` फाइल से पूरा टेक्स्ट कॉपी करके पेस्ट करें।
3. **App icon**:
   - `play_store/assets/app_icon_512.png` फाइल अपलोड करें (512x512)।
4. **Feature graphic**:
   - `play_store/assets/feature_graphic_1024x500.png` फाइल अपलोड करें (1024x500)।
5. **Phone screenshots**:
   - कम से कम 2 से 4 स्क्रीनशॉट (अपने फोन या ब्राउज़र के Academics और Drilldown स्क्रीन) अपलोड करें।
6. **Save** पर क्लिक करें।

---

## 🚢 Step 6: App Bundle (.aab) अपलोड करना और पब्लिश करना

1. बाईं तरफ मेनू में जाएं: **Release > Production**।
2. ऊपर **"Create new release"** पर क्लिक करें।
3. **App bundles**:
   - Step 2 में बनाई गई **`app-release.aab`** फाइल को ड्रैग एंड ड्रॉप करके अपलोड करें।
4. **Release name**: `1.0.0 (Initial Release)`
5. **Release notes**:
   ```
   Initial official release of SmartVision Idea Lab attendance & DigiCampus academic portal.
   ```
6. नीचे **Next** > **Review release** पर क्लिक करें।
7. **"Start rollout to Production"** पर क्लिक करें!

🎉 **बधाई हो!** आपकी ऐप अब Google Play Review टीम के पास चली जाएगी। आमतौर पर 24 से 48 घंटे के भीतर गूगल ऐप को अप्रूव कर देता है और वह पूरी दुनिया के लिए Google Play Store पर लाइव हो जाती है!
