#!/usr/bin/env python3
"""
Fetches daily USD close prices for the 977 tickers in the global ETF universe sheet
(Global_Unique_Equity_ETFs_v2.xlsx) and writes data/global-etf-history.json in the shape
the Global ETF Heatmap tab expects:

    { "<TICKER>": [["YYYY-MM-DD", price], ...], ... }

Tickers already carry their Yahoo Finance exchange suffix where needed (.L London,
.DE Frankfurt, .PA Paris, .T Tokyo, .SW Zurich, .MI Milan, .MC Madrid) — no suffix is
added here, unlike the NSE-only fetch_etf_data.py script.

Only ~14 months of history is kept (LOOKBACK) to keep the JSON file a reasonable size
across 977 tickers — enough for the tab's default trailing-52-week view plus some room
either side for a custom date range.

Run locally with:  python3 scripts/fetch_global_etf_data.py
Runs automatically via .github/workflows/update-data.yml on a daily schedule.
No API key needed — yfinance reads Yahoo Finance's public endpoints.
"""
import json
import time

import yfinance as yf

TICKERS = [
    "SPY","QQQ","XLF","XLE","SCHD","EEM","EWZ","IWM","FXI","XLU","EWY","1306.T",
    "IGV","KRE","XLB","EFA","XLP","VEA","SMH","XLV","XBI","SCHX","XLK","RSP",
    "CTEC.L","SCHF","VWO","XLY","SCHG","XLI","SCHB","VUG","JPST","ICLN","IJH","ISF.L",
    "XLC","VXUS","INDA","EWT","XLRE","HDV","IWF","EWJ","XRT","VGT","1545.T","DIA",
    "VNQ","EFV","IJR","SCHV","VTI","QQQM","XOP","SCHE","IHI","VO","EWH","VTV",
    "SPDW","FNDX","VEU","SCHA","ACWI","ILF","VT","CNYA.L","EWA","EMXC","XHB","SPLV",
    "SPMO","ITB","XME","IWD","USMV","VGK","AIQ","PAVE","SPSM","FINA","SPEM","IWR",
    "EWC","IDEV","KBWB","FXN","FNDF","CIBR","ITOT","IVW","SPHQ","JPIE","MTUM","EUFN",
    "KBE","SCZ","BBJP","SPMD","IQLT","DGRO","XLG","SASU.L","EIDO","MGK","SCHM","FENY",
    "EWU","VYM","KIE","VLUE","FNDE","EWW","SHLD","SCHK","NOBL","IYZ","RDVY","CQQQ",
    "DTCR","EWS","QUAL","EWG","SEMI.L","IEUR","FNDA","WCMI","EZU","VYMI","FEZ","IYE",
    "FDL","IGF","IXC","IWP","IVLU","SPHD","FCG","PICK","FTXN","XUSE.L","AIRR","IYH",
    "KLMN","IDV","1489.T","ESGE","EFG","REMX","WEBN.DE","IVE","IYT","ITA","FTXH","VNM",
    "MDY","MOAT","GRID","FBCG","IUSV","VDE","IYW","IWN","ARTY","586A.T","IHF","QNDX",
    "FVD","IWB","URTH","AAXJ","VFH","1678.T","MIDD.L","EFAV","VB","IUSG","EWL","SPTM",
    "JQUA","KSA","AIA","IWO","ECH","IWS","FTCS","EPOL","IWX","KBWD","VPL","IXN",
    "CLOU","FUTY","NLR","EWI","SDIV","WSML.L","IYF","XMMO","ESGU","IEZ","CRAK","VXF",
    "EWP","FNDB","IWY","IUKD.L","IDMO","1321.T","IMTM","IGM","BNKS.L","VOX","SCHC","TOPT",
    "JIVE","EWQ","FFSM","EWD","MOO","SAEM.L","OIH","BBEU","EPP","VOE","PRF","JTEK",
    "IOO","IHE","VPU","XSMO","FDN","VNQI","FTEC","IJS","ROCY","PPH","ONEQ","ROCQ",
    "MGV","VBR","SMMD","IXJ","FXU","GRE.PA","EMLP","FHLC","IJK","POWR","VHT","DIVB",
    "FCOM","OEF","INTF","LTAM.L","XAR","EWN","WHCA.L","PXH","IJT","EWM","VV","SUSM.L",
    "EEMV","BBCA","VSS","IYM","UAE","BBAX","JGLO","VBK","EMMUSC.SW","SPGM","DIV","QCLN",
    "WENS.L","SDY","TRUT","VOT","PPA","GPZ","EWZS","IYK","STAR.L","DFND.L","SLYV","BBUS",
    "IGE","EPHE","BBIN","IJJ","GXPC","EWJV","ESGV","VSGX","IWV","IEVL.L","AINF.L","FXL",
    "SMLF","EZA","XMHQ","COLO","IAT","EMGF","GXPT","TDIV","VDC","ARGT","IDHQ","EEMA",
    "LRGF","DVYE","QQQJ","PTF","JEMA","IDU","IAK","XPH","FTXR","DFEU.L","FIDU","JMOM",
    "JFLX","SMIN","QTOP","TUR","DEFS.PA","IDRV","FSTA","IYJ","SLYG","PWV","FDT","ICOP",
    "ZAP","IWVL.L","FSMD","PXF","VIS","FNCL","DSI","FTGS","HEAL.L","FFLG","KXI","PWB",
    "EDIV","SMDV","WQDV.L","605A.T","IEO","FAN","FEM","CNXT","LOCK.L","ENZL","IEV","IYC",
    "PRFZ","ACWV","IYG","FNDC","PIE","MISL","PHO","RWJ","ENOR","MDYV","WMVG.L","FFLC",
    "EQWL","FIVA","IDNA","MDYG","FTXO","PIZ","MGC","SPGP","JPEF","FDEM","BLKC.L","RDIV",
    "FDIS","XASX.DE","XES","IAI","EUSA","FYC","KOMP","FINX","PXJ","PEJ","FHEQ","XTN",
    "FDMO","FIDI","IKOR.L","FV","EWO","XTL","WGDP.DE","IWC","EEMS","AFK","JVAL","IXG",
    "PTH","TRUD","REGL","SPYX","FXH","SUJP.L","SSAC.L","THD","EXI","GWX","VFMF","VAW",
    "AUSF","EMVL.L","IXP","ILDR","FMAT","XNTK","VCR","HYDR","EIS","IUS","AGED.L","BUZZ",
    "IDVY.L","WARP","IFV","FIW","IAPD.L","GXPD","XSW","FPXI","TRUC","XLSR","VEGI","AIAA.L",
    "FEMS","FDTX","FCA","FDLO","JXI","PRN","FXO","IWL","FVAL","PNQI","159A.T","XSHQ",
    "PSCT","IPKW","FXZ","EPU","FPX","BBRE","IDX","2513.T","EELV","SCJ","LGDS","RACK",
    "MAXJ","IGRO","PJP","FRI","EFNL","EIPX","IMVP","IFSU.L","FTRI","XSVM","IWMO.L","F50A.DE",
    "HAP","PKB","XMAW.DE","ORBX","SVAL","BBEM","FQAL","BNK.PA","IETC","DAX","MXI","SPOG.L",
    "PSP","DXSA.DE","XDWT.DE","FXR","EWK","EQAL","IDLV","LITM.L","FTA","IFFF.L","IBBQ","XMVM",
    "FYX","DGIT.L","TENJ","PBJ","JIG","IBAT","FDEV","XHS","QANT.L","XHE","WEBA.DE","FTAW.L",
    "XSHD","PSCH","SLX","PRAM.DE","CGW","EWX","WIRE.DE","FREI","KCE","GXC","IVVM","JULV",
    "SPEU","GLOF","GXPS","PDP","VEXC","PXE","CAC.PA","IYY","UNIC.PA","XDWF.DE","ASEA","PGJ",
    "PSCE","AASI.PA","FCPI","SMOT","PXI","FEX","HSMV","JPSE","HUSV","FNY","QAT","DWX",
    "LGLV","FDNI","LCAS.MI","EFAS","XDWS.DE","1311.T","1325.T","RXI","FEP","QEW","KBWP","FAB",
    "DWAS","FMAG","HERO","QQMG","XMLV","IVVB","IPRV.L","FTHF","PSCI","SNSR","JPRE","MADE",
    "XJH","ISVL","EQRR","EDOW","FFEM","IFSD.L","FTC","JPEM","FFGX","XWTS.DE","EMMV.L","ILIT",
    "MATW.PA","WELG.DE","VFMV","FBCV","TOLZ","LCTD","BNKE.PA","FBOT","FYT","PRUK.L","BBMC","2514.T",
    "FID","MTAV.L","FAD","INDB.DE","EMDM","INDEP.PA","CSD","AGNG","PRAE.DE","FXG","FNX","AWHD.DE",
    "ILCB","PSCC","PFI","XUTC.DE","PR1J.DE","FLN","FICS","IEQU.L","518A.T","FXD","SADA.DE","2846.T",
    "FBDC","TINY","2529.T","FTXG","XDN0.DE","WELD.DE","PUI","EDEN","DGT","JPME","MAXD.L","PLAY.L",
    "BBSC","QABA","PDN","ECNS","WCME","FPA","FJP","FDM","EIRL","DDIV","XSLV","LCUK.DE",
    "2520.T","IEMD.L","XJR","HEAL","EMXU.PA","XSMI.DE","NXTG","412A.T","IFSW.L","VNAM","TECB","SOCL",
    "CEFA","MTRA","FDIF","CT2B.L","VDV","NRJ.PA","KROP","MILN","FPWR","GMF","JPIN","VLU",
    "WDIV","RBLD","EPAB.PA","BLDR.L","EVX","DMAX","EMXF","SMAX","GLIN","FBUF","QRMI","XDND.DE",
    "FSCS","JPUS","VDG","FTCE","JPXN","AEJ.PA","FMED","JOYT","IAEX.L","MVED.L","MIB.PA","FDCF",
    "WELM.DE","QQQS","ONOF","IEUS","EMET","ISTM","EMXCN.SW","WOOD.L","AQWA","PRAZ.DE","DVOL","ONLN",
    "EDGX","MDUC.DE","BKF","TWOX","C007.DE","OPEN.L","MAXM.L","TDV","DALI","CSTK","MLCC","XMOV.DE",
    "QBIG","CSM","BRF","MOTI","RTH","SIZE","DVLU","FNK","TOK","WAT.PA","EMC","F50C.DE",
    "LVDS","NRGW.PA","FMTL","KWT","CVY","RND","RNRG","JFLI","MMSC","TEKX","FDFF","FFLV",
    "CPTL","LYXIB.MC","USDB.L","CARZ","SDG","1577.T","XPND","ELCR.PA","IDJG.L","ISRA","BRIC.L","PSCF",
    "RCTR","ENRG.PA","WELY.DE","IPXJ.L","FLOW","GXDW","ERTH","NYSX","FEUZ","KNCT","EBIZ","SDEM",
    "MMAX","STEN","POWA","IBRN","FTAG","MDEV","XUEK.DE","FVC","FDIQ","PDJE.PA","TELW.PA","ESCE.L",
    "WELC.DE","SMLV","GLIT.PA","WCMG","EMIF","WELT.DE","XITK","FFDI","TRV.PA","XUCM.DE","CZA","2518.T",
    "CTEC","DGIN","VEEM","TEXN","1319.T","INDZ","QOWZ","QTR","PYZ","10AJ.DE","TENM","DJSC.L",
    "DAT","FTSE.PA","DJMC.L","FCTR","ITAMID.MI","ION","C003.DE","C5E.PA","FKU","LEGR","FGM","INAA.L",
    "C005.DE","QQHG","PAWZ","FTDS","AEXX.PA","CUT","PSCM","FSPC","FTIF","KDOM.L","UPGD","JLVP",
    "IGSG.L","SMOG","PSCU","EKG","KLMT","GENZ","1546.T","PSL","FMI.PA","PMTL","GURU","LDEM",
    "MEH.PA","JDIV","MAXS.L","CSUK.L","SCDS","LFEQ","XIFE.DE","ISFE.L","QQLV","MRGR","FSGS","ELLE.PA",
    "FSZ","SGQI.PA","C006.DE","FDTS","MMTM","PAF.PA","SUPL","HDMV","EFRA","MOTG","XEMN.DE","BMVP",
    "SPDG","MWO.PA","TRUH","XNZN.DE","SDG9.DE","BNGE","MCDS","CLIX","DGLO","PEZ","C030.DE","2643.T",
    "XGLF.DE","EGUSAS.SW","GXPE","XCNY","SHRY","XDRE.DE","ETEC","XG12.DE","NRAM.PA","PSCD","XDG3.DE","TEND.L",
    "JIDE","FPXE","TINT","MVAL","METL.L","RNEM","1559.T","XNGI.DE","EBUY.PA","EUDIV.PA","TRUO","TRUF",
    "XZSP.DE","DTRE","JDOC","XFNT.DE","TRUN","SPXPW.SW","TRUM","DXSG.DE","OND","TRUI","LCDS","MILL.PA",
    "CWE.PA","1560.T","ACUU.DE","GXLC","ANEW","SCITY.PA","TRUU","IQSZ","LUXU.PA","TRUR","XNZW.DE","KFOR.L",
    "XDGI.DE","ISHP","TMDV","DVVY","XG11.DE","XZEC.DE","CHM.PA","XNNV.DE","XBUZ.DE","XDGS.DE","XEPA.DE","1309.T",
    "XNUS.DE","294A.T","1480.T","EURP.L","UMDV.L","COPM.L","EUFG.L","JPDV.L","EXXV.L","EXXX.L","EXXU.L","EXI2.L",
    "EXX1.L","EXI1.L","EXSD.L","EXSC.L","EXS2.L","EXSE.L","DFCU.L","TLCO.L","OM3X.L","CSUKS.L","STOR.L","SPDM",
    "QNXT.L","SPLT","NUUR.L","AU2.PA","XNJG.DE","SDG6.DE","XSDX.DE","CLIMA.SW","GINC.SW","AW12.SW","AW1J.SW","UETE.SW",
    "BCFW.SW","CHTE.SW","RSX","RSXJ","639A.T",
]

OUT_PATH = "data/global-etf-history.json"
LOOKBACK = "14mo"
# Small batches + no threading + real pauses between calls — Yahoo Finance rate-limits
# (HTTP 429) hard once a runner fires off a big grouped/threaded download, and after the
# first request or two gets throttled every subsequent batch in the run silently returns
# empty data. Slower but far more reliable across 977 tickers.
BATCH_SIZE = 20
RETRIES = 4
SLEEP_BETWEEN_BATCHES = 4.0
SLEEP_ON_RETRY = 12.0


def fetch_batch(tickers):
    out = {}
    raw = None
    for attempt in range(RETRIES):
        try:
            raw = yf.download(tickers, period=LOOKBACK, interval="1d", auto_adjust=True,
                               group_by="ticker", threads=False, progress=False)
            if raw is not None and len(raw) > 0:
                break
        except Exception as e:
            print(f"  batch download attempt {attempt+1} failed: {e}")
            raw = None
        time.sleep(SLEEP_ON_RETRY * (attempt + 1))
    if raw is None or len(raw) == 0:
        return out
    single = len(tickers) == 1
    for t in tickers:
        try:
            s = raw["Close"] if single else raw[t]["Close"]
            s = s.dropna()
            if len(s) > 0:
                out[t] = [[d.strftime("%Y-%m-%d"), round(float(c), 4)] for d, c in s.items()]
        except Exception:
            continue
    return out


def main():
    result = {}
    missing = []
    n_batches = (len(TICKERS) - 1) // BATCH_SIZE + 1
    for i in range(0, len(TICKERS), BATCH_SIZE):
        batch = TICKERS[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        got = fetch_batch(batch)
        result.update(got)
        missing.extend([t for t in batch if t not in got])
        print(f"Batch {batch_num}/{n_batches}: got {len(got)}/{len(batch)} — running total {len(result)}")
        # Save progress after every batch so a mid-run failure/timeout still leaves
        # whatever was fetched so far, instead of losing the whole run's data.
        with open(OUT_PATH, "w") as f:
            json.dump(result, f, separators=(",", ":"))
        time.sleep(SLEEP_BETWEEN_BATCHES)

    print(f"Wrote {OUT_PATH}: {len(result)}/{len(TICKERS)} tickers.")
    if missing:
        print(f"Missing ({len(missing)}): {missing[:30]}{'...' if len(missing) > 30 else ''}")


if __name__ == "__main__":
    main()
