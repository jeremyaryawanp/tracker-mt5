//+------------------------------------------------------------------+
//| TradeJournal AI - MT4 history exporter (READ-ONLY)                 |
//| Sends closed tickets from the account history to the web app.      |
//| It never calls OrderSend/OrderModify/OrderClose.                   |
//|                                                                    |
//| Setup: Tools > Options > Expert Advisors > "Allow WebRequest for   |
//| listed URL" and add your TradeJournal URL. Set the Account History |
//| tab to "All History". Attach the EA to any chart.                  |
//+------------------------------------------------------------------+
#property strict
#property description "TradeJournal AI read-only history exporter"

input string InpUrl            = "http://127.0.0.1:8000/api/v1/ingest/mt4";
input string InpToken          = "";     // ingest token from the Accounts page
input int    InpIntervalSec    = 300;    // push interval
input int    InpServerOffsetMin= -99999; // -99999 = auto (TimeCurrent - TimeGMT)
input bool   InpWriteCsv       = false;  // also write MQL4/Files/tradejournal_history.csv

int OnInit()
{
   if(StringLen(InpToken) == 0) { Print("TradeJournal: set InpToken"); return(INIT_PARAMETERS_INCORRECT); }
   EventSetTimer(MathMax(InpIntervalSec, 60));
   PushHistory();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }
void OnTimer() { PushHistory(); }

string Esc(string s)
{
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   return s;
}

string Iso(datetime t) { return TimeToString(t, TIME_DATE|TIME_SECONDS); }  // server time, naive

string Sha256Hex(string text)
{
   uchar src[], key[], dst[];
   StringToCharArray(text, src, 0, StringLen(text));
   if(CryptEncode(CRYPT_HASH_SHA256, src, key, dst) <= 0) return "";
   string hex = "";
   for(int i = 0; i < ArraySize(dst); i++) hex += StringFormat("%02x", dst[i]);
   return hex;
}

void PushHistory()
{
   int offset = InpServerOffsetMin;
   if(offset == -99999) offset = (int)MathRound((TimeCurrent() - TimeGMT()) / 1800.0) * 30;
   string login = Sha256Hex("MT4:" + AccountServer() + ":" + IntegerToString(AccountNumber()));
   string json = "{\"account\":{\"platform\":\"MT4\",\"login_hash\":\"" + login + "\"," +
      "\"broker_name\":\"" + Esc(AccountCompany()) + "\",\"broker_server\":\"" + Esc(AccountServer()) + "\"," +
      "\"currency\":\"" + AccountCurrency() + "\"},\"server_utc_offset_minutes\":" + IntegerToString(offset) +
      ",\"tickets\":[";
   int fh = INVALID_HANDLE;
   if(InpWriteCsv)
   {
      fh = FileOpen("tradejournal_history.csv", FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(fh != INVALID_HANDLE)
         FileWrite(fh, "ticket","symbol","type","volume","open_time","open_price","close_time",
                   "close_price","sl","tp","commission","swap","profit","comment");
   }
   int n = 0;
   for(int i = 0; i < OrdersHistoryTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      int type = OrderType();
      if(type > 1 && type != 6 && type != 7) continue;
      if(n > 0) json += ",";
      json += "{\"ticket\":\"" + IntegerToString(OrderTicket()) + "\",\"symbol\":\"" + OrderSymbol() + "\"," +
         "\"type\":" + IntegerToString(type) + ",\"lots\":" + DoubleToString(OrderLots(), 2) + "," +
         "\"open_time\":\"" + Iso(OrderOpenTime()) + "\"," +
         (OrderCloseTime() > 0 ? "\"close_time\":\"" + Iso(OrderCloseTime()) + "\"," : "") +
         "\"open_price\":" + DoubleToString(OrderOpenPrice(), 8) + ",\"close_price\":" + DoubleToString(OrderClosePrice(), 8) + "," +
         "\"sl\":" + DoubleToString(OrderStopLoss(), 8) + ",\"tp\":" + DoubleToString(OrderTakeProfit(), 8) + "," +
         "\"commission\":" + DoubleToString(OrderCommission(), 2) + ",\"swap\":" + DoubleToString(OrderSwap(), 2) + "," +
         "\"profit\":" + DoubleToString(OrderProfit(), 2) + ",\"magic\":" + IntegerToString(OrderMagicNumber()) + "," +
         "\"comment\":\"" + Esc(OrderComment()) + "\"}";
      if(fh != INVALID_HANDLE)
         FileWrite(fh, OrderTicket(), OrderSymbol(), type == 0 ? "buy" : (type == 1 ? "sell" : "balance"),
                   OrderLots(), Iso(OrderOpenTime()), OrderOpenPrice(), Iso(OrderCloseTime()), OrderClosePrice(),
                   OrderStopLoss(), OrderTakeProfit(), OrderCommission(), OrderSwap(), OrderProfit(), OrderComment());
      n++;
   }
   json += "]}";
   if(fh != INVALID_HANDLE) FileClose(fh);

   char body[], result[];
   string respHeaders;
   StringToCharArray(json, body, 0, StringLen(json));
   string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + InpToken + "\r\n";
   int status = WebRequest("POST", InpUrl, headers, 30000, body, result, respHeaders);
   if(status == -1) Print("TradeJournal: WebRequest failed, error ", GetLastError(), " (is the URL allowed?)");
   else Print("TradeJournal: pushed ", n, " tickets, HTTP ", status, " ", CharArrayToString(result));
}
