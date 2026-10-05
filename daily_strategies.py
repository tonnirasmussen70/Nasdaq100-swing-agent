from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "reports" / "daily_strategies_latest.json"

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d=s.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-(100/(1+up/dn.replace(0,np.nan)))

def atr(df: pd.DataFrame,n:int=14)->pd.Series:
    pc=df["Close"].shift(1)
    tr=pd.concat([(df["High"]-df["Low"]).abs(),(df["High"]-pc).abs(),(df["Low"]-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def universe()->list[str]:
    tables=pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
    for x in tables:
        for c in x.columns:
            if str(c).lower() in {"ticker","symbol"}:
                return x[c].astype(str).str.replace(".","-",regex=False).tolist()
    raise RuntimeError("Nasdaq-100 universe not found")

def one(ticker:str, ndx_ret_63:float):
    d=yf.download(ticker,period="1y",interval="1d",auto_adjust=True,progress=False)
    if d.empty or len(d)<210:return None
    if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
    c=d["Close"]; v=d["Volume"]; a=atr(d); rr=rsi(c)
    sma50=c.rolling(50).mean(); sma200=c.rolling(200).mean(); ema20=c.ewm(span=20,adjust=False).mean()
    ret63=c.iloc[-1]/c.iloc[-64]-1
    trend=bool(c.iloc[-1]>sma200.iloc[-1] and sma50.iloc[-1]>sma200.iloc[-1] and sma50.iloc[-1]>sma50.iloc[-6])
    pullback=trend and c.iloc[-1]>=sma50.iloc[-1]*0.97 and c.iloc[-1]<=ema20.iloc[-1]*1.03 and c.iloc[-1]<c.rolling(20).max().iloc[-1]*0.98 and rr.iloc[-1]>rr.iloc[-2]
    prev20=c.shift(1).rolling(20).max()
    volratio=float(v.iloc[-1]/v.rolling(20).mean().iloc[-1]) if v.rolling(20).mean().iloc[-1] else np.nan
    breakout=trend and c.iloc[-1]>prev20.iloc[-1] and ret63>ndx_ret_63 and volratio>=1.5
    av=float(a.iloc[-1]); px=float(c.iloc[-1])
    base={"ticker":ticker,"close":round(px,2),"rsi14":round(float(rr.iloc[-1]),1),"atr14":round(av,2),"return_3m_pct":round(ret63*100,1),"rs_vs_ndx_3m_pct":round((ret63-ndx_ret_63)*100,1),"volume_ratio":round(volratio,2)}
    p=dict(base); p.update({"entry":round(px,2),"stop":round(px-1.75*av,2),"target_2r":round(px+3.5*av,2)})
    b=dict(base); breakout_stop=max(float(prev20.iloc[-1])-0.5*av,px-1.75*av); b.update({"entry":round(px,2),"stop":round(breakout_stop,2),"target_2r":round(px+2*(px-breakout_stop),2)})
    return p if pullback else None,b if breakout else None

def main():
    ndx=yf.download("^NDX",period="6mo",interval="1d",auto_adjust=True,progress=False)
    if isinstance(ndx.columns,pd.MultiIndex):ndx.columns=ndx.columns.get_level_values(0)
    nr=float(ndx["Close"].iloc[-1]/ndx["Close"].iloc[-64]-1)
    pull=[]; br=[]; failures=[]
    for ticker in universe():
        try:
            p,b=one(ticker,nr)
            if p:pull.append(p)
            if b:br.append(b)
        except Exception: failures.append(ticker)
    pull.sort(key=lambda x:(x["return_3m_pct"],-x["rsi14"]),reverse=True)
    br.sort(key=lambda x:(x["rs_vs_ndx_3m_pct"],x["volume_ratio"]),reverse=True)
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"mode":"paper_observation","pullback":pull,"breakout":br,"data_failures":failures}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print(f"pullback={len(pull)} breakout={len(br)} failures={len(failures)}")

if __name__=="__main__": main()
