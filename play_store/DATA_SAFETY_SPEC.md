# Google Play Console - Data Safety Questionnaire Responses

Use this exact cheat sheet when filling out the mandatory **Data safety** section in the Google Play Console for **SmartVision: DigiCampus Idea Lab**.

---

### Question 1: Data collection and security
- **Does your app collect or share any of the required user data types?**
  - 👉 **Yes**
- **Is all of the user data collected by your app encrypted in transit?**
  - 👉 **Yes** (All web communication is encrypted using HTTPS / TLS 1.3).
- **Do you provide a way for users to request that their data be deleted?**
  - 👉 **Yes** (Through the in-app "Right to be Forgotten" erasure request form and via grievance officer email).
- **Does your app provide a link for users to request data deletion?**
  - 👉 **Yes**: `https://idea-lab-project-69.vercel.app/privacy#data-rights`

---

### Question 2: Data Types Breakdown

#### A. Personal Info
1. **Name**:
   - Collected: **Yes**
   - Shared: **No**
   - Ephemeral: **No**
   - Is this data required for your app, or can users choose whether it's collected?
     - 👉 **App functionality** (Required for identifying students on the academic roster).
2. **Email Address**:
   - Collected: **Yes**
   - Shared: **No**
   - Ephemeral: **No**
   - Purpose: **Account management** & **App functionality**.
3. **User IDs (Roll Number / Student ID)**:
   - Collected: **Yes**
   - Shared: **No**
   - Purpose: **App functionality** (Unique college identity mapping).

#### B. Photos and Videos
1. **Photos (Profile Portrait)**:
   - Collected: **Yes**
   - Shared: **No**
   - Ephemeral: **No**
   - Purpose: **App functionality** (Used exclusively for visual roster display and face biometric enrollment).

#### C. Biometric Information
1. **Biometric Data (Facial recognition embeddings)**:
   - Collected: **Yes**
   - Shared: **No** (Processed and stored securely on institutional server).
   - Ephemeral: **No** (Stored until student graduates or requests deletion).
   - Purpose: **App functionality** (Automated contactless lab attendance verification).

---

### Question 3: Data Sharing
- **Do you share any user data with third parties (ad networks, data brokers, tracking SDKs)?**
  - 👉 **NO**. SmartVision contains zero advertising, zero marketing trackers, and zero third-party commercial SDKs.

---

### Question 4: Advertising ID
- **Does your app use the Android Advertising ID (AAID)?**
  - 👉 **NO**.
