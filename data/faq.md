# Travel Reimbursement — FAQ & Edge Case Handling
**Purpose:** Guides the AI agent in handling ambiguous, incomplete, or unusual claims.

---

## Q1: What if the city is not listed in per_diem_limits.csv?

**Answer:** Use the nearest major metro city limits based on geography.
- Example: Mysuru → use Bangalore limits
- Example: Nashik → use Pune limits
- Flag the claim with: `"city_not_in_policy": true`
- Route to **Manual Review** if the amount is significant (> ₹5,000)

---

## Q2: What if receipts are partially missing?

**Answer:** Apply tiered handling per policy Section 5:
- Amount ≤ ₹200: Approve without receipt
- Amount ₹201–₹500 without receipt: Reimburse at **50%**, note deduction
- Amount > ₹500 without receipt: **Reject** that line item
- If missing receipts total > 30% of claim value: Route to **Manual Review**

---

## Q3: What if the expense category is unclear or unlisted?

**Answer:**
- Try to map to the closest eligible category
- If mapping is ambiguous: Flag as `"ambiguous_category": true`
- Route to **Manual Review** with reason: "Expense category unclear — requires human verification"
- Never auto-reject an ambiguous category; always escalate

---

## Q4: What if the employee grade is not in approval_matrix.csv?

**Answer:**
- Default to **L1** (most restrictive) limits
- Add flag: `"grade_not_found": true`
- Escalate to manager for verification

---

## Q5: What if the claim is submitted after 30 days?

**Answer:**
- Check submission_date vs travel_end_date
- If gap > 30 days: Flag as `"late_submission": true`
- Route to **Manual Review** — manager approval required
- Do not auto-reject; manager may override

---

## Q6: What if multiple ineligible items are present?

**Answer:**
- Reject each ineligible line item individually
- If eligible items remain: Issue **Partial Approval** for eligible portion
- If all items are ineligible: Issue **Reject**
- Always list each rejected item with specific reason

---

## Q7: What if total claim is within limits but a single item is very high?

**Answer:**
- Evaluate each line item independently against its category cap
- Flag the anomalous item: `"anomaly_flag": true`
- Proceed with normal approval if within policy
- Add note in explanation: "Item reviewed — within policy limits"

---

## Q8: International trip with INR amounts (no forex conversion)?

**Answer:**
- Assume amounts already converted to INR unless currency field specified
- If currency field present and not INR: Apply RBI reference rate (use rate from config or approximate)
- Flag: `"currency_converted": true`

---

## Q9: What if the employee notes mention "emergency" or "stolen receipts"?

**Answer:**
- Do not auto-reject
- Route to **Manual Review** with reason: "Employee claims emergency — manager verification required"
- This matches Section 8 of policy (Emergency Expenses)

---

## Q10: Confidence scoring guidance

| Situation | Confidence |
|---|---|
| All receipts present, all within limits | High |
| Minor deductions, 1 item over limit | High |
| Missing 1-2 receipts, some items near limit | Medium |
| Missing critical receipts (flight/hotel) | Low → Manual Review |
| Ineligible items + missing docs | Low → Reject or Manual Review |
| Ambiguous categories or unlisted city | Low → Manual Review |
