---

# Technical Philosophy: The Self-Directed Build

**Carlymarie992**

> "Quality is not an act, it is a habit." — Aristole (Applied to Python)

### 1. The "Need-to-Know" Architecture

I approach coding through the lens of **Information Utility**. Before importing a library, I ask: *Does this reduce friction for the end-user?*

* **Example:** I pivoted from `PyPDF2` to `pypdf 3.17.1` because reliability in legal data extraction is a non-negotiable user requirement. If the data is buggy, the UX is broken.

### 2. Radical Reproducibility

As a self-taught developer, my "credential" is code that works on *your* machine the same way it works on mine.

* I maintain strict versioning (e.g., `pandas>=2.0.0`) and isolated environments (`venv`).
* I prioritize **Boltons** and **Standard Libraries** to ensure my builds are robust and minimize "dependency hell."

### 3. Data as Narrative (UX of Data)

I believe that a raw dataset is a UX failure. My philosophy is to use **Matplotlib** and **Seaborn** to translate complex behavioral patterns into "at-a-glance" insights.

* **The Goal:** To move a user from *confusion* to *conclusion* in under 5 seconds.

### 4. Continuous Iteration Cycle

My learning curriculum follows a strict **Build-Audit-Refine** loop:

1. **Build:** Solve a real-world problem (e.g., Coercive Control analysis).
2. **Audit:** Analyze the code for efficiency, security (`cryptography`), and clear logic.
3. **Refine:** Rewrite for clarity and "Plain English" documentation.

---
