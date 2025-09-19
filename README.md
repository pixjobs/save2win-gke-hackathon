# 🏆 Save2Win: Your Personal Finance Quest

Transforming savings from a chore into a rewarding adventure — with an AI-powered financial coach built on **Google Kubernetes Engine (GKE)**.  

---

## 🎯 Hackathon Info  
- **Hackathon**: GKE Turns 10 Hackathon  
- **Team**: Pixjobs  
- **Submission**: Original work created for the hackathon  

---

## 🚀 Live Demo & Video  
- **Hosted Demo**: [LINK TO YOUR HOSTED DEMO]  
- **Video Walkthrough (3 min)**: [LINK TO YOUTUBE/VIMEO DEMO]  

---

## 💡 The Problem  
Saving money feels like **work**:  
- Traditional apps show numbers, not **motivation**.  
- Users struggle to connect small sacrifices to meaningful long-term rewards.  
- Trust is fragile — people hesitate to let apps manage their money.  

---

## ✅ The Save2Win Solution  
Save2Win is a **gamified AI microservice** built on top of the **Bank of Anthos** application.  

It acts as an **AI Financial Coach** that:  
- Makes saving **fun and rewarding** with quests, XP, and badges  
- Builds **trust** by analysing data only — *it never touches your money*  
- Sustains motivation with **dynamic quests, streaks, and seasonal challenges**  

---

## ✨ Key Features  

- 🎮 **Gamified Savings**: Earn XP for deposits and smart spending. Level up your financial health!  
- 🧭 **AI-Powered Quests**: Gemini generates creative challenges (e.g., *“Coffee Crusader: Make coffee at home 4 times this week for 500 XP!”*).  
- 💡 **Motivational Insights**: Daily “Did you know?” tips show how small wins add up to big rewards.  
- 🏅 **Achievement Badges**: Unlock milestones like *First $1,000 Saved* or *Savings Streak Master*.  
- 🔒 **Built-In Trust**: Save2Win never handles transactions. It only reads context through MCP, leaving core banking untouched.  
- 🔄 **Sustained Motivation**: Beyond badges, users get:  
  - **Savings streaks** → keep going week to week  
  - **Seasonal quests** → fresh challenges tied to events (e.g., “Summer Saver Sprint”)  
  - **Community leaderboards** (optional) → friendly competition  
  - **Real-world goals** → AI helps map savings to exciting milestones like travel or gadgets  

---

## 🏛️ Architecture & Tech Stack  

| Category | Technology | Purpose |
|----------|------------|---------|
| **Orchestration** | Google Kubernetes Engine (GKE) | Deploy/manage microservices (Bank of Anthos + Save2Win) |
| **AI Model** | Google Gemini | AI coach: quest generation + motivational insights |
| **Agent Framework** | Agent Development Kit (ADK) | Agent foundation for Save2Win Engine |
| **Context Broker** | Model Context Protocol (MCP) | Decouples agent from APIs, ensures data privacy |
| **Backend Service** | Python (Flask), Docker | Save2Win Engine microservice |
| **Frontend** | React, Nginx, Docker | Gamified dashboard for XP, quests, and badges |
| **CI/CD** | Skaffold, Cloud Code for VS Code | Rapid build/deploy workflow |

---

## 🔄 How It Works  

1. User interacts with the **Save2Win Dashboard**.  
2. Frontend calls the **Save2Win Engine** (Flask, ADK).  
3. Engine queries the **MCP Server** for transaction context (no direct access to banking APIs).  
4. MCP securely retrieves data from Bank of Anthos APIs.  
5. Engine sends anonymised context to **Gemini**, which generates:  
   - Personalized savings quest  
   - Motivational financial tip  
6. Engine applies **game logic** (XP, streaks, seasonal challenges, achievements).  
7. Frontend displays the updated financial “game state.”  

💡 **Why trust matters**: Save2Win never moves or controls money — it only **reads context**. This separation makes it safe to integrate without risk.  

---

## ⚙️ Getting Started  

### Prerequisites  
- Google Cloud SDK (`gcloud`)  
- `kubectl`  
- Skaffold  
- Docker  
- A running GKE cluster  

### Installation  

\`\`\`bash
# Clone repo (with submodules)
git clone --recurse-submodules [YOUR_GITHUB_REPO_URL]
cd save2win-gke-hackathon

# Point kubectl to GKE cluster
gcloud container clusters get-credentials <YOUR_CLUSTER>

# Set Gemini API Key
export GEMINI_API_KEY=your_api_key

# Deploy everything
skaffold run
\`\`\`

### Access  
\`\`\`bash
kubectl get services
\`\`\`
Use the external IP of \`frontend-service\` to open the Save2Win dashboard.  

---

## 🏅 Bonus Hackathon Contributions  
- **Blog / Explainer**: [LINK TO DEV.TO, MEDIUM, OR VIDEO]  
- **Social Media Post**: [LINK TO TWEET/LINKEDIN with #GKEHackathon]  

---

# 📝 Why This Use Case Works  

✅ **Trustworthy**: Clear separation — no money moved, only insights.  
✅ **Motivating**: Keeps users engaged with streaks, seasonal quests, and leaderboards.  
✅ **Scalable**: Microservice + MCP means new data sources can be added easily.  
✅ **Hackathon-ready**: Fun, visual, and easy to demo.  

---

👉 With trust and sustained motivation built in, Save2Win isn’t just a hackathon project — it’s a **blueprint for a new generation of engaging, safe, AI-powered finance apps**.  
