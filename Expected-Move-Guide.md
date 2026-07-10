# Expected Move Calculation: A Beginner's Guide to Options Volatility

*A practical reference for understanding implied volatility, expected moves, and probability-based trading*

---

## Table of Contents

1. What is Implied Volatility?
2. The Expected Move Formula
3. Standard Deviations and Probability
4. Reading the Options Chain
5. ATM Options and Expected Move
6. The Straddle Shortcut
7. VIX and the S&P 500
8. Practical Applications
9. Common Misconceptions
10. Formula Reference Card

---

## 1. What is Implied Volatility (IV)?

Implied volatility is the market's forecast of how much a stock is likely to move. It answers: "How big of a move does the options market expect?"

**Key characteristics:**

- **Forward-looking** -- unlike historical volatility (what already happened), IV tells you what the market expects will happen
- **Annualized** -- always expressed as a yearly percentage, regardless of the option's timeframe
- **Non-directional** -- tells you the magnitude of expected movement, not whether it's up or down
- **Derived from options prices** -- IV is "reverse-engineered" from what people are actually paying for options

**How it works conceptually:**

If a stock is at $100 and has an IV of 30%, the market expects approximately a $30 move (up or down) over the next year. That's the 1-standard-deviation annual range: roughly $70 to $130.

**IV vs. Historical Volatility (HV):**

| Measure | Direction | Based On | Tells You |
|---------|-----------|----------|-----------|
| Implied (IV) | Forward | Current options prices | What the market expects |
| Historical (HV) | Backward | Past price movements | What actually happened |

Research consistently shows that IV tends to trade at a slight premium to realized (historical) volatility. In other words, options tend to be slightly "overpriced" relative to actual movement -- which is why options selling strategies exist.

---

## 2. The Expected Move Formula

The expected move converts annualized IV into a dollar-amount price range for a specific time period.

### The Core Formula

```
Expected Move = Stock Price x IV x sqrt(Days / Trading Days in Year)
```

Or more precisely:

```
Expected Move = Price x IV x sqrt(DTE / 252)
```

Where:
- **Price** = current stock price
- **IV** = implied volatility as a decimal (20% = 0.20)
- **DTE** = days to expiration (trading days)
- **252** = trading days in a year

### The Daily Shortcut

Since sqrt(252) is approximately 16:

```
Daily Expected Move = (Price x IV) / 16
```

**Quick mental math:** A stock with 16% IV has a daily expected move of 1% of its price. ($100 stock x 0.16 / 16 = $1.00)

### Time Period Conversions

| Period | Formula | Example ($100 stock, 20% IV) |
|--------|---------|-------------------------------|
| Annual | Price x IV | $100 x 0.20 = $20.00 |
| Monthly | Price x IV / sqrt(12) | $100 x 0.20 / 3.46 = $5.78 |
| Weekly | Price x IV x sqrt(5) / sqrt(252) | $100 x 0.20 x 2.24 / 15.87 = $2.82 |
| Daily | Price x IV / sqrt(252) | $100 x 0.20 / 15.87 = $1.26 |

### To-Expiration (Any Number of Days)

```
Expected Move = Price x IV x sqrt(DTE) / sqrt(252)
```

Example: $100 stock, 30% IV, 45 days to expiration:
- EM = $100 x 0.30 x sqrt(45) / sqrt(252)
- EM = $100 x 0.30 x 6.71 / 15.87
- EM = $12.68

This means the market expects the stock to stay within +/- $12.68 of its current price with ~68% probability over the next 45 days.

---

## 3. Standard Deviations and Probability

The expected move formula gives you a **one standard deviation (1-sigma)** range. Here's what that means in terms of probability:

### The 68-95-99.7 Rule

| Range | Probability WITHIN | Probability OUTSIDE | What it means |
|-------|-------------------|--------------------|----|
| 1 sigma | 68.3% | 31.7% | Stock stays within the expected move ~2 out of 3 times |
| 2 sigma | 95.4% | 4.6% | Stock stays within 2x the expected move ~19 out of 20 times |
| 3 sigma | 99.7% | 0.3% | Stock stays within 3x the expected move ~369 out of 370 times |

### Applying to Expected Move

If a $100 stock has a daily expected move of $2.00:

| Level | Range | Probability |
|-------|-------|-------------|
| 1 sigma (+/- $2) | $98 to $102 | 68% chance stock stays here |
| 2 sigma (+/- $4) | $96 to $104 | 95% chance stock stays here |
| 3 sigma (+/- $6) | $94 to $106 | 99.7% chance stock stays here |

### The Reality Check

The 68-95-99.7 rule assumes a perfect normal distribution. In real markets:

- **Fat tails** -- extreme moves (3+ sigma) happen more often than the math predicts
- **Volatility clustering** -- big moves tend to follow big moves
- **Skew** -- large down moves are more common than large up moves

This means: trust the 1-sigma range as a useful guide, but don't bet your account on the 3-sigma "never happens" assumption.

---

## 4. Reading the Options Chain

The options chain is the table showing all available options contracts for a stock.

### Layout

```
           CALLS                    STRIKE         PUTS
  Bid  Ask  Last  Vol  OI  IV   |  PRICE  |  IV  OI  Vol  Last  Ask  Bid
 5.20 5.40 5.30  1200 8500 28%  |  $100   | 28% 9200 1400 5.15 5.35 5.10
 3.80 4.00 3.90   800 6200 30%  |  $105   | 26% 5800  600 7.80 8.00 7.60
 2.50 2.70 2.60   600 4100 32%  |  $110   | 24% 3200  400 11.50 11.80 11.30
```

### Key Columns

| Column | What It Means | Why You Care |
|--------|--------------|--------------|
| **Strike** | The price at which you can buy/sell the stock | Defines your contract |
| **Bid/Ask** | Buyer's price / Seller's price | The spread = your cost to enter |
| **IV** | Implied volatility for that specific strike | Higher = market expects bigger moves |
| **Volume** | Contracts traded today | Liquidity indicator |
| **Open Interest** | Total outstanding contracts | Deeper OI = tighter spreads |
| **Delta** | Probability of finishing in-the-money | 0.50 = ATM, 0.30 = ~30% chance ITM |

### Finding the ATM Option

The **at-the-money (ATM)** option is the strike price closest to the current stock price. This is the most important one for expected move because:

- It has the highest time/volatility premium
- It's the most liquid
- Its IV is the "headline" IV for the stock
- Its delta is approximately 0.50

---

## 5. ATM Options and Expected Move

The ATM option is the cornerstone of expected move calculations.

### Why ATM Matters

When you hear "Stock XYZ has 30% implied volatility," that number comes from the ATM option. It's the purest measure of expected movement because:

1. ATM options have the most **extrinsic value** (time + volatility premium)
2. They're the most **liquid** -- tightest bid/ask spreads
3. Their price most directly reflects the market's volatility expectation
4. They have **delta near 0.50** -- equal probability of finishing above or below

### The IV Smile/Skew

In reality, IV is not the same at every strike price:

```
  IV
  |         /
  |        /
  |   ____/
  |  /
  | /
  |/______________ Strike Price
     OTM Puts    ATM    OTM Calls
```

- **OTM puts** (lower strikes) typically have HIGHER IV -- this is the "skew"
- Reason: investors pay more for downside protection (crash insurance)
- This means the probability distribution is not perfectly symmetric -- the market prices in larger down moves

---

## 6. The Straddle Shortcut

There's an even faster way to estimate expected move without doing any math:

### The Rule

```
Expected Move (approx) = ATM Call Price + ATM Put Price
```

That's it. The price of the ATM straddle IS the market's expected move.

### Why This Works

- A straddle buyer pays for both a call and a put at the same strike
- The buyer only profits if the stock moves MORE than the total premium paid
- Market makers set prices so the straddle represents the "fair" expected move
- The breakeven points of the straddle define the 1-sigma range

### Example

Stock at $100. ATM call costs $3.50, ATM put costs $3.20.

- Straddle cost = $3.50 + $3.20 = $6.70
- Expected move = approximately $6.70
- Expected range by expiration: $93.30 to $106.70

### When to Use Each Method

| Method | Best For | Advantage |
|--------|----------|-----------|
| IV formula | Precise calculations, custom time periods | Exact math for any DTE |
| Straddle | Quick read of market expectations, earnings plays | No math needed, real-time |

---

## 7. VIX and the S&P 500

The VIX (CBOE Volatility Index) is the expected move calculation applied to the entire S&P 500.

### What VIX Is

- The market's expected annualized movement of the S&P 500 over the next 30 days
- Calculated from SPX option prices (not individual stock options)
- Often called the "Fear Gauge" -- spikes when markets sell off

### Converting VIX to Expected Moves

```
Daily S&P 500 Expected Move = SPX Price x (VIX / 100) / sqrt(252)
```

Or with the shortcut:

```
Daily S&P 500 Expected Move = SPX Price x (VIX / 100) / 16
```

**Example:** S&P 500 at 7,500 with VIX at 16:
- Daily expected move = 7,500 x 0.16 / 16 = 75 points (+/- 1%)
- Weekly expected move = 7,500 x 0.16 x sqrt(5) / 16 = 168 points (+/- 2.2%)

### VIX Interpretation

| VIX Level | Market Regime | Daily SPX Expected Move (at 7,500) |
|-----------|--------------|-------------------------------------|
| 10-12 | Extremely calm | +/- 47-56 pts (0.6-0.7%) |
| 12-16 | Low/normal | +/- 56-75 pts (0.7-1.0%) |
| 16-20 | Moderate | +/- 75-94 pts (1.0-1.3%) |
| 20-25 | Elevated concern | +/- 94-117 pts (1.3-1.6%) |
| 25-35 | High volatility | +/- 117-164 pts (1.6-2.2%) |
| 35-50 | Crisis/panic | +/- 164-234 pts (2.2-3.1%) |
| 50+ | Extreme panic | +/- 234+ pts (3.1%+) |

### Key VIX Relationships

- VIX has a **strong inverse correlation** with the S&P 500 -- when stocks fall, VIX spikes
- VIX tends to **mean-revert** -- extreme highs eventually come down
- VIX **futures** often trade above spot VIX (contango) -- the market prices in future uncertainty

---

## 8. Practical Applications

### A. "Is my price target realistic?"

Before setting a target, check the expected move:
- If expected move to your target date is $5, a $15 target has very low probability
- Use the 1-sigma range as your "realistic" zone

### B. Options Selling: Where to Place Strikes

Sell options **outside** the expected move for high probability:

| Strategy | Short Strike Placement | Approx. Probability of Profit |
|----------|----------------------|-------------------------------|
| At 1 sigma | At the expected move boundary | ~68% |
| At 1.5 sigma | 1.5x the expected move | ~87% |
| At 2 sigma | 2x the expected move | ~95% |

Example: Stock at $100, expected move = $8 by expiration.
- Sell the $108 call and $92 put (iron condor at 1 sigma) = ~68% POP
- Sell the $112 call and $88 put (at 1.5 sigma) = ~87% POP
- Sell the $116 call and $84 put (at 2 sigma) = ~95% POP

Trade-off: wider strikes = higher probability but less premium collected.

### C. Earnings Plays

Earnings announcements often cause large moves. The market prices this in:

1. Check the ATM straddle price before earnings (this is the "priced-in" move)
2. Compare to historical earnings moves for that stock
3. If historical average is 5% but straddle implies 8%: options may be overpriced (favor selling)
4. If historical average is 8% but straddle implies 5%: options may be underpriced (favor buying)

### D. Position Sizing with Expected Move

Use expected move to size positions so a bad outcome doesn't blow up your account:

```
Max Position Size = (Account Risk %) / (Expected Move x Leverage Factor)
```

Example: $100K account, willing to risk 2% ($2,000), stock has daily expected move of $3:
- If you're holding overnight, a 2-sigma move = $6
- Max shares = $2,000 / $6 = 333 shares

### E. Stop Loss Placement

- Setting stops INSIDE the expected move means you'll get stopped out frequently (noise)
- Setting stops at 1.5-2x the expected move gives room for normal fluctuation
- Consider: a 1-sigma stop triggers ~32% of the time (too often for most strategies)

---

## 9. Common Misconceptions

### "The stock WILL move the expected amount"

**Wrong.** Expected move defines a probabilistic range. The stock might move 0, or it might move 5x the expected amount. It's a probability distribution, not a prediction.

### "68% probability means I'll win 68% of the time"

**Incomplete.** It means the stock stays WITHIN the range 68% of the time. But the 32% when it goes outside can produce losses that overwhelm many small wins. This is why pure probability-based selling doesn't guarantee profitability.

### "A 3-sigma event basically never happens"

**Dangerous.** In theory, a 3-sigma daily move should happen about once every 370 trading days (~1.5 years). In reality, markets have "fat tails" -- extreme events happen far more often than a normal distribution predicts. The 2020 pandemic crash produced multiple 5+ sigma days in a single week.

### "Higher IV means the stock will move more"

**Not necessarily.** Higher IV means the market EXPECTS a bigger move and is pricing options accordingly. But IV can be "wrong" -- a stock with 50% IV might only move 20% (IV overstated), or a 15% IV stock might suddenly move 40% (IV understated).

### "IV is constant across all strikes and expirations"

**Wrong.** IV varies by:
- **Strike price** (volatility smile/skew -- OTM puts usually have higher IV)
- **Expiration date** (term structure -- near-term IV often differs from long-term)
- **Time of day** (IV often rises into the close and falls at open)
- **Events** (IV spikes before earnings, FDA decisions, etc.)

### "The square root of time scaling is exact"

**It's an approximation.** The sqrt(time) rule assumes price changes are independent and identically distributed (like coin flips). In reality, volatility clusters -- high-volatility days tend to follow high-volatility days. The formula works well as a guide but not as a physical law.

---

## 10. Formula Reference Card

### Core Formulas

```
DAILY EXPECTED MOVE
  = Price x IV / sqrt(252)
  = Price x IV / 16          [shortcut]

WEEKLY EXPECTED MOVE
  = Price x IV x sqrt(5) / sqrt(252)
  = Price x IV x 2.236 / 16  [shortcut]

TO-EXPIRATION EXPECTED MOVE
  = Price x IV x sqrt(DTE) / sqrt(252)

STRADDLE APPROXIMATION
  = ATM Call Price + ATM Put Price

VIX TO DAILY S&P MOVE
  = SPX Price x (VIX/100) / 16
```

### Probability Ranges

```
1-sigma: Price +/- EM        --> 68.3% probability within
2-sigma: Price +/- (2 x EM)  --> 95.4% probability within
3-sigma: Price +/- (3 x EM)  --> 99.7% probability within
```

### Quick IV Mental Math

```
16% IV = 1.0% daily expected move
20% IV = 1.25% daily expected move
25% IV = 1.56% daily expected move
30% IV = 1.88% daily expected move
40% IV = 2.50% daily expected move
50% IV = 3.13% daily expected move
```

### Key Constants

```
sqrt(252) = 15.87  (trading days in a year)
sqrt(365) = 19.10  (calendar days in a year)
sqrt(5)   = 2.236  (trading days in a week)
sqrt(12)  = 3.464  (months in a year)
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **ATM** | At-the-money: option whose strike equals the stock price |
| **DTE** | Days to expiration: calendar days until the option expires |
| **IV** | Implied volatility: annualized expected move derived from option prices |
| **HV** | Historical volatility: actual past movement of the stock |
| **Sigma** | Standard deviation: one unit of expected movement |
| **Straddle** | Buying both an ATM call and ATM put at the same strike |
| **Skew** | The difference in IV across different strike prices |
| **VIX** | CBOE Volatility Index: the S&P 500's implied volatility |
| **OTM** | Out-of-the-money: calls above / puts below current price |
| **ITM** | In-the-money: calls below / puts above current price |
| **Delta** | Probability of an option finishing in-the-money |
| **Premium** | The price paid for an options contract |
| **Extrinsic Value** | The portion of an option's price attributable to time + volatility |

---

*Guide generated: 2026-07-10*
*Sources: CBOE, Investopedia, Options Playbook, CFI, Wikipedia (Black-Scholes, VIX, Implied Volatility)*
