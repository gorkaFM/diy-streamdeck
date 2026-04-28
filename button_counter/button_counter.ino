#include "LGFX_ESP32S3_RGB_ESP32-8048S043.h"
#include <Preferences.h>
#define USE_NIMBLE
#include <BleKeyboard.h>

LGFX lcd;
Preferences prefs;
BleKeyboard bleKb("StreamDeck", "BitsyTornillos", 100);

// ─── Layout ───
static const int SIDEBAR_W = 56;
static const int GRID_W = 800 - SIDEBAR_W;
static const int COLS = 4;
static const int ROWS = 3;
static const int NUM_BUTTONS = COLS * ROWS;
static const int NUM_PAGES = 3;
static const int PAD = 10;
static const int BTN_W = (GRID_W - (COLS + 1) * PAD) / COLS;
static const int BTN_H = (480 - (ROWS + 1) * PAD) / ROWS;
static const int RADIUS = 12;
static const int SB_X = GRID_W;
static const int SB_ITEM_H = 60;
static const int SB_ITEMS = 6;
static const uint16_t SB_BG = 0x1082;
static const int ICON_SIZES[] = {24, 32, 48, 64};

// Touch swipe
static const int SWIPE_DX = 80;
static const int SWIPE_MAX_DY = 60;
static const int TAP_TOLERANCE = 20;

struct Button {
  char label[20];
  uint8_t r, g, b;
  char action[128];
  uint8_t actionType;  // 0=none, 1=url, 2=keyboard, 3=app, 4=text
  uint8_t iconSizeIdx, borderStyle;
  bool showLabel;
};

Button buttons[NUM_PAGES][NUM_BUTTONS];
uint16_t* iconData[NUM_PAGES][NUM_BUTTONS];
bool hasIcon[NUM_PAGES][NUM_BUTTONS];
int iconPixelSize[NUM_PAGES][NUM_BUTTONS];
char pageNames[NUM_PAGES][24];
int currentPage = 0;
int activeButton = -1;
int activeSidebar = -1;
bool locked = false;
bool infoShown = false;
uint8_t brightness = 255;

// Touch state
enum TouchPhase { TP_IDLE, TP_PRESS, TP_SWIPE };
TouchPhase tphase = TP_IDLE;
int32_t tStartX = 0, tStartY = 0, tLastX = 0, tLastY = 0;
int tBtn = -1, tSb = -1;

static const char* defaultLabels[] = {"1","2","3","4","5","6","7","8","9","10","11","12"};
static const uint8_t defaultColors[][3] = {
  {231,76,60},{46,204,113},{52,152,219},{241,196,15},
  {155,89,182},{230,126,34},{26,188,156},{236,64,122},
  {52,73,94},{127,140,141},{39,174,96},{41,128,185},
};

// ─── Base64 ───
int b64val(char c){if(c>='A'&&c<='Z')return c-'A';if(c>='a'&&c<='z')return c-'a'+26;if(c>='0'&&c<='9')return c-'0'+52;if(c=='+')return 62;if(c=='/')return 63;return -1;}
int base64_decode(const char*in,int inLen,uint8_t*out,int outMax){int o=0;uint32_t buf=0;int bits=0;for(int i=0;i<inLen&&o<outMax;i++){int v=b64val(in[i]);if(v<0)continue;buf=(buf<<6)|v;bits+=6;if(bits>=8){bits-=8;out[o++]=(buf>>bits)&0xFF;}}return o;}

// ─── Config ───
// Global index helpers: gi = page*NUM_BUTTONS + idx, range 0..35
static inline int gidx(int p, int i){return p*NUM_BUTTONS+i;}

void saveOne(int p, int i){
  prefs.begin("deck",false);
  int g=gidx(p,i);char k[10];
  snprintf(k,10,"l%d",g);prefs.putString(k,buttons[p][i].label);
  snprintf(k,10,"r%d",g);prefs.putUChar(k,buttons[p][i].r);
  snprintf(k,10,"g%d",g);prefs.putUChar(k,buttons[p][i].g);
  snprintf(k,10,"b%d",g);prefs.putUChar(k,buttons[p][i].b);
  snprintf(k,10,"a%d",g);prefs.putString(k,buttons[p][i].action);
  snprintf(k,10,"y%d",g);prefs.putUChar(k,buttons[p][i].actionType);
  snprintf(k,10,"z%d",g);prefs.putUChar(k,buttons[p][i].iconSizeIdx);
  snprintf(k,10,"d%d",g);prefs.putUChar(k,buttons[p][i].borderStyle);
  snprintf(k,10,"t%d",g);prefs.putBool(k,buttons[p][i].showLabel);
  prefs.end();
}

void saveBrightness(){prefs.begin("deck",false);prefs.putUChar("bri",brightness);prefs.end();}

void savePageName(int p){
  if(p<0||p>=NUM_PAGES)return;
  prefs.begin("deck",false);
  char k[8];snprintf(k,8,"pn%d",p);
  prefs.putString(k,pageNames[p]);
  prefs.end();
}

void loadConfig(){
  prefs.begin("deck",true);
  for(int p=0;p<NUM_PAGES;p++){
    for(int i=0;i<NUM_BUTTONS;i++){
      int g=gidx(p,i);char k[10];
      snprintf(k,10,"l%d",g);String lbl=prefs.getString(k,defaultLabels[i]);strncpy(buttons[p][i].label,lbl.c_str(),19);buttons[p][i].label[19]='\0';
      snprintf(k,10,"r%d",g);buttons[p][i].r=prefs.getUChar(k,defaultColors[i][0]);
      snprintf(k,10,"g%d",g);buttons[p][i].g=prefs.getUChar(k,defaultColors[i][1]);
      snprintf(k,10,"b%d",g);buttons[p][i].b=prefs.getUChar(k,defaultColors[i][2]);
      snprintf(k,10,"a%d",g);String act=prefs.getString(k,"");strncpy(buttons[p][i].action,act.c_str(),127);buttons[p][i].action[127]='\0';
      snprintf(k,10,"y%d",g);buttons[p][i].actionType=prefs.getUChar(k,0);
      snprintf(k,10,"z%d",g);buttons[p][i].iconSizeIdx=prefs.getUChar(k,1);
      snprintf(k,10,"d%d",g);buttons[p][i].borderStyle=prefs.getUChar(k,0);
      snprintf(k,10,"t%d",g);buttons[p][i].showLabel=prefs.getBool(k,true);
    }
  }
  brightness=prefs.getUChar("bri",255);
  for(int p=0;p<NUM_PAGES;p++){
    char k[8];snprintf(k,8,"pn%d",p);
    char defname[24];snprintf(defname,24,"Pagina %d",p+1);
    String n=prefs.getString(k,defname);
    strncpy(pageNames[p],n.c_str(),23);
    pageNames[p][23]='\0';
  }
  prefs.end();
}

// ─── BLE Keyboard Actions ───
void sendKeyCombo(const char*combo){
  if(!bleKb.isConnected())return;
  String s=String(combo);s.toLowerCase();
  if(s=="vol_up"){bleKb.write(KEY_MEDIA_VOLUME_UP);return;}
  if(s=="vol_down"){bleKb.write(KEY_MEDIA_VOLUME_DOWN);return;}
  if(s=="vol_mute"){bleKb.write(KEY_MEDIA_MUTE);return;}
  if(s=="play_pause"){bleKb.write(KEY_MEDIA_PLAY_PAUSE);return;}
  if(s=="next_track"){bleKb.write(KEY_MEDIA_NEXT_TRACK);return;}
  if(s=="prev_track"){bleKb.write(KEY_MEDIA_PREVIOUS_TRACK);return;}
  bool ctrl=false,shift=false,alt=false,gui=false;int last=-1;
  while(true){int p=s.indexOf('+',last+1);if(p<0)break;String m=s.substring(last+1,p);m.trim();
    if(m=="ctrl"||m=="control")ctrl=true;else if(m=="shift")shift=true;
    else if(m=="alt"||m=="option")alt=true;else if(m=="cmd"||m=="command"||m=="win"||m=="gui"||m=="super"||m=="meta")gui=true;last=p;}
  String key=s.substring(last+1);key.trim();
  if(ctrl)bleKb.press(KEY_LEFT_CTRL);if(shift)bleKb.press(KEY_LEFT_SHIFT);
  if(alt)bleKb.press(KEY_LEFT_ALT);if(gui)bleKb.press(KEY_LEFT_GUI);
  if(key.length()==1)bleKb.press(key[0]);
  else if(key=="enter"||key=="return")bleKb.press(KEY_RETURN);
  else if(key=="esc")bleKb.press(KEY_ESC);else if(key=="tab")bleKb.press(KEY_TAB);
  else if(key=="space")bleKb.press(' ');else if(key=="backspace"||key=="delete")bleKb.press(KEY_BACKSPACE);
  else if(key=="up")bleKb.press(KEY_UP_ARROW);else if(key=="down")bleKb.press(KEY_DOWN_ARROW);
  else if(key=="left")bleKb.press(KEY_LEFT_ARROW);else if(key=="right")bleKb.press(KEY_RIGHT_ARROW);
  else if(key=="prtsc"||key=="printscreen")bleKb.press((uint8_t)0xCE);  // HID 0x46 + lib offset
  else if(key.startsWith("f")&&key.length()<=3){int f=key.substring(1).toInt();if(f>=1&&f<=12)bleKb.press(KEY_F1+f-1);}
  delay(50);bleKb.releaseAll();}

void executeAction(int idx){
  int p=currentPage;
  if(idx<0||idx>=NUM_BUTTONS||buttons[p][idx].actionType==0||strlen(buttons[p][idx].action)==0)return;
  Serial.printf("[ACT] P%d Btn %d type=%d action=%s\n",p,idx,buttons[p][idx].actionType,buttons[p][idx].action);

  // Always notify host (with page) so the desktop app can open URL/app
  Serial.printf("BTN:%d:%d:%d:%s\n", p, idx, buttons[p][idx].actionType, buttons[p][idx].action);

  switch(buttons[p][idx].actionType) {
    case 1: // URL - handled by host
    case 3: // App - handled by host
      break;
    case 2: // Keyboard shortcut
      sendKeyCombo(buttons[p][idx].action);
      break;
    case 4: // Text
      if(bleKb.isConnected()) bleKb.print(buttons[p][idx].action);
      break;
  }
}

// ─── Sidebar icons ───
void drawGearIcon(int cx,int cy,uint16_t col){lcd.fillCircle(cx,cy,8,col);lcd.fillCircle(cx,cy,4,SB_BG);for(int a=0;a<360;a+=45){float r=a*3.14159/180;lcd.fillCircle(cx+cos(r)*11,cy+sin(r)*11,3,col);}}
void drawSunIcon(int cx,int cy,uint16_t col,bool big){int r=big?7:5;lcd.fillCircle(cx,cy,r,col);int rl=big?13:10;for(int a=0;a<360;a+=45){float rd=a*3.14159/180;lcd.drawLine(cx+cos(rd)*(r+2),cy+sin(rd)*(r+2),cx+cos(rd)*rl,cy+sin(rd)*rl,col);}}
void drawLockIcon(int cx,int cy,uint16_t col,bool isLocked){lcd.fillRoundRect(cx-8,cy-2,16,12,2,col);if(isLocked)lcd.drawArc(cx,cy-2,7,5,180,360,col);else lcd.drawArc(cx+3,cy-2,7,5,180,360,col);lcd.fillCircle(cx,cy+3,2,SB_BG);}
void drawArrow(int cx,int cy,bool right,uint16_t col){
  // Filled triangle 12 wide, 14 tall
  if(right){lcd.fillTriangle(cx-6,cy-7,cx-6,cy+7,cx+7,cy,col);}
  else     {lcd.fillTriangle(cx+6,cy-7,cx+6,cy+7,cx-7,cy,col);}
}

void drawSidebar(){
  lcd.fillRect(SB_X,0,SIDEBAR_W,480,SB_BG);
  lcd.drawFastVLine(SB_X,0,480,lcd.color565(40,40,50));
  int cx=SB_X+SIDEBAR_W/2;int y=0;
  uint16_t lblCol=lcd.color565(120,120,130);
  lcd.setTextDatum(middle_center);lcd.setFont(&fonts::Font0);

  // 0: BLE status
  bool conn=bleKb.isConnected();
  lcd.fillCircle(cx,y+22,6,conn?lcd.color565(0,150,255):lcd.color565(80,80,80));
  if(conn){lcd.drawCircle(cx,y+22,8,lcd.color565(0,70,130));lcd.drawCircle(cx,y+22,10,lcd.color565(0,35,65));}
  lcd.setTextColor(lblCol);lcd.drawString(conn?"BT OK":"BT...",cx,y+42);
  y+=SB_ITEM_H;lcd.drawFastHLine(SB_X+8,y,SIDEBAR_W-16,lcd.color565(40,40,50));

  // 1: Page nav. Top row: arrows + "N/3". Middle: name (8 chars). Bottom: dots.
  drawArrow(SB_X+10,y+12,false,lcd.color565(180,180,200));
  drawArrow(SB_X+SIDEBAR_W-10,y+12,true,lcd.color565(180,180,200));
  char pbuf[8];snprintf(pbuf,8,"%d/%d",currentPage+1,NUM_PAGES);
  lcd.setTextColor(lcd.color565(220,220,230));lcd.drawString(pbuf,cx,y+12);
  // Page name (truncated)
  char nbuf[10];
  strncpy(nbuf,pageNames[currentPage],9);nbuf[9]='\0';
  lcd.setTextColor(lcd.color565(255,220,120));
  lcd.drawString(nbuf,cx,y+34);
  // 3 dots indicator
  for(int i=0;i<NUM_PAGES;i++){
    int dx=cx-((NUM_PAGES-1)*5)+i*10;
    uint16_t dc=(i==currentPage)?lcd.color565(100,180,255):lcd.color565(60,60,80);
    lcd.fillCircle(dx,y+50,2,dc);
  }
  y+=SB_ITEM_H;lcd.drawFastHLine(SB_X+8,y,SIDEBAR_W-16,lcd.color565(40,40,50));

  // 2: Config gear
  drawGearIcon(cx,y+22,lcd.color565(180,180,200));
  lcd.setTextColor(lblCol);lcd.drawString("Config",cx,y+42);
  y+=SB_ITEM_H;lcd.drawFastHLine(SB_X+8,y,SIDEBAR_W-16,lcd.color565(40,40,50));

  // 3: Brillo+
  drawSunIcon(cx,y+22,lcd.color565(255,220,50),true);lcd.setTextColor(lblCol);lcd.drawString("Brillo+",cx,y+42);
  y+=SB_ITEM_H;
  // 4: Brillo-
  drawSunIcon(cx,y+22,lcd.color565(150,130,30),false);lcd.setTextColor(lblCol);lcd.drawString("Brillo-",cx,y+42);
  y+=SB_ITEM_H;lcd.drawFastHLine(SB_X+8,y,SIDEBAR_W-16,lcd.color565(40,40,50));

  // 5: Lock
  uint16_t lc=locked?lcd.color565(231,76,60):lcd.color565(120,120,140);
  drawLockIcon(cx,y+22,lc,locked);
  lcd.setTextColor(locked?lcd.color565(231,76,60):lblCol);
  lcd.drawString(locked?"Bloq":"Libre",cx,y+42);

  // Brightness bar
  int bx=SB_X+10,bw=SIDEBAR_W-20;
  lcd.fillRoundRect(bx,440,bw,6,3,lcd.color565(40,40,50));
  lcd.fillRoundRect(bx,440,(brightness*bw)/255,6,3,lcd.color565(255,220,50));
  char buf[8];snprintf(buf,8,"%d%%",(brightness*100)/255);
  lcd.setTextColor(lcd.color565(100,100,110));lcd.drawString(buf,cx,458);
}

int sidebarHitTest(int32_t tx,int32_t ty){
  if(tx<SB_X)return-1;
  int item=ty/SB_ITEM_H;
  if(item<0||item>=SB_ITEMS)return -1;
  return item;
}

// Forward decls
void drawAll();
void drawInfoScreen();
void hideInfoScreen();
void changePage(int newPage);

void handleSidebarTouch(int item, int32_t tx){
  switch(item){
    case 0: // BT status - no action
      break;
    case 1: { // Page nav: left half = prev, right half = next
      bool right = (tx > SB_X + SIDEBAR_W/2);
      int np = currentPage + (right?1:-1);
      if(np<0) np = NUM_PAGES-1;
      if(np>=NUM_PAGES) np = 0;
      changePage(np);
      break;
    }
    case 2: // Config gear
      if(infoShown) hideInfoScreen();
      else { drawInfoScreen(); Serial.println("BTN:0:99:1:https://github.com/gorkaFM/diy-streamdeck"); }
      break;
    case 3: brightness=min(255,brightness+30);lcd.setBrightness(brightness);saveBrightness();drawSidebar();break;
    case 4: brightness=max(25,brightness-30);lcd.setBrightness(brightness);saveBrightness();drawSidebar();break;
    case 5: locked=!locked;drawSidebar();break;
  }
}

// ─── Buttons ───
void getBtnRect(int idx,int&x,int&y){x=PAD+(idx%COLS)*(BTN_W+PAD);y=PAD+(idx/COLS)*(BTN_H+PAD);}
void drawBorder(int bx,int by,int w,int h,uint8_t s,uint8_t cr,uint8_t cg,uint8_t cb){if(s==0)return;uint16_t bc=lcd.color565(min(255,cr+80),min(255,cg+80),min(255,cb+80));if(s==1)lcd.drawRoundRect(bx,by,w,h,RADIUS,bc);else if(s==2)for(int i=0;i<3;i++)lcd.drawRoundRect(bx+i,by+i,w-i*2,h-i*2,RADIUS-i,bc);else if(s==3)for(int g=4;g>=0;g--){uint8_t a=60+(4-g)*45;lcd.drawRoundRect(bx-g,by-g,w+g*2,h+g*2,RADIUS+g,lcd.color565(min(255,(int)cr+a),min(255,(int)cg+a),min(255,(int)cb+a)));}}

void drawButton(int idx,bool pressed){
  int p=currentPage;
  int bx,by;getBtnRect(idx,bx,by);
  uint8_t r=buttons[p][idx].r,g=buttons[p][idx].g,b=buttons[p][idx].b;
  uint16_t color=pressed?lcd.color565(r*0.6,g*0.6,b*0.6):lcd.color565(r,g,b);
  int yOff=pressed?3:0;
  lcd.fillRect(bx-5,by-5,BTN_W+14,BTN_H+16,TFT_BLACK);
  if(!pressed)lcd.fillRoundRect(bx+3,by+3,BTN_W,BTN_H,RADIUS,lcd.color565(20,20,20));
  lcd.fillRoundRect(bx,by+yOff,BTN_W,BTN_H,RADIUS,color);
  drawBorder(bx,by+yOff,BTN_W,BTN_H,buttons[p][idx].borderStyle,r,g,b);
  int cx=bx+BTN_W/2;
  if(hasIcon[p][idx]&&iconData[p][idx]){
    int sz=iconPixelSize[p][idx],ix=cx-sz/2;
    if(buttons[p][idx].showLabel){lcd.pushImage(ix,by+yOff+(BTN_H/2)-sz/2-10,sz,sz,iconData[p][idx]);lcd.setTextColor(TFT_WHITE);lcd.setTextDatum(middle_center);lcd.setFont(&fonts::Font2);lcd.drawString(buttons[p][idx].label,cx,by+yOff+BTN_H-20);}
    else lcd.pushImage(ix,by+yOff+(BTN_H-sz)/2,sz,sz,iconData[p][idx]);
  }else if(buttons[p][idx].showLabel){lcd.setTextColor(TFT_WHITE);lcd.setTextDatum(middle_center);lcd.setFont(&fonts::Font4);lcd.drawString(buttons[p][idx].label,cx,by+yOff+BTN_H/2);}
}

void drawAll(){lcd.fillRect(0,0,GRID_W,480,TFT_BLACK);for(int i=0;i<NUM_BUTTONS;i++)drawButton(i,false);drawSidebar();}

void changePage(int newPage){
  if(newPage<0||newPage>=NUM_PAGES||newPage==currentPage)return;
  currentPage=newPage;
  if(infoShown){infoShown=false;}
  drawAll();
  Serial.printf("[PAGE] %d\n",currentPage);
  Serial.printf("PAGE:%d\n",currentPage); // notify host
}

int hitTest(int32_t tx,int32_t ty){if(tx>=SB_X)return-1;for(int i=0;i<NUM_BUTTONS;i++){int bx,by;getBtnRect(i,bx,by);if(tx>=bx&&tx<=bx+BTN_W&&ty>=by&&ty<=by+BTN_H)return i;}return-1;}

// ─── Serial protocol ───
// New (with page): SET:<page>:<idx>:..., ACT:<page>:<idx>:..., ICON:<page>:<idx>:..., GETALL, PAGE:<n>, NOICON:<page>:<idx>
// Output: BTN:<page>:<idx>:<type>:<action>, CFG:<page>:<idx>:..., PAGE:<n>
static char sBuf[14000];
static int sLen=0;

int sFindCh(char ch,int from){for(int i=from;i<sLen;i++)if(sBuf[i]==ch)return i;return-1;}
int sToInt(int from,int to){char t[12];int n=min(to-from,11);memcpy(t,sBuf+from,n);t[n]=0;return atoi(t);}

void processCmd(){
  while(sLen>0&&(sBuf[sLen-1]==' '||sBuf[sLen-1]=='\t'))sLen--;
  sBuf[sLen]=0;
  if(sLen==0)return;

  Serial.printf("[CMD] %.*s (%d)\n",min(sLen,40),sBuf,sLen);

  if(sLen==6&&memcmp(sBuf,"GETALL",6)==0){
    for(int p=0;p<NUM_PAGES;p++)
      Serial.printf("PNAME:%d:%s\n",p,pageNames[p]);
    for(int p=0;p<NUM_PAGES;p++){
      for(int i=0;i<NUM_BUTTONS;i++){
        Serial.printf("CFG:%d:%d:%s:%d,%d,%d:%d:%d,%d,%d:%d:%s\n",
          p,i,buttons[p][i].label,
          buttons[p][i].r,buttons[p][i].g,buttons[p][i].b,
          hasIcon[p][i]?1:0,
          buttons[p][i].iconSizeIdx,buttons[p][i].borderStyle,buttons[p][i].showLabel?1:0,
          buttons[p][i].actionType,buttons[p][i].action);
      }
    }
    Serial.printf("CURPAGE:%d\n",currentPage);
    Serial.println("END");return;
  }

  // PNAME:<page>:<text>  set page name (max 23 chars)
  if(sLen>=6&&memcmp(sBuf,"PNAME:",6)==0){
    int p1=sFindCh(':',6);if(p1<0)return;
    int page=sToInt(6,p1);if(page<0||page>=NUM_PAGES)return;
    int nl=min(sLen-p1-1,23);
    memcpy(pageNames[page],sBuf+p1+1,nl);
    pageNames[page][nl]='\0';
    savePageName(page);
    if(page==currentPage&&!infoShown)drawSidebar();
    Serial.println("OK");return;
  }

  // SET:<page>:<idx>:<label>:<r>,<g>,<b>:<sz>,<brd>,<lbl>
  if(sLen>=4&&memcmp(sBuf,"SET:",4)==0){
    int p1=sFindCh(':',4);if(p1<0)return;
    int p2=sFindCh(':',p1+1);if(p2<0)return;
    int p3=sFindCh(':',p2+1);if(p3<0)return;
    int page=sToInt(4,p1);if(page<0||page>=NUM_PAGES)return;
    int idx=sToInt(p1+1,p2);if(idx<0||idx>=NUM_BUTTONS)return;
    int ll=min(p3-p2-1,19);memcpy(buttons[page][idx].label,sBuf+p2+1,ll);buttons[page][idx].label[ll]='\0';
    int c1=sFindCh(',',p3+1),c2=sFindCh(',',c1+1);if(c1<0||c2<0)return;
    int nc=sFindCh(':',c2+1);int ce=(nc>=0)?nc:sLen;
    buttons[page][idx].r=sToInt(p3+1,c1);buttons[page][idx].g=sToInt(c1+1,c2);buttons[page][idx].b=sToInt(c2+1,ce);
    if(nc>=0){
      int s1=sFindCh(',',nc+1),s2=sFindCh(',',s1+1);
      if(s1>=0&&s2>=0){
        buttons[page][idx].iconSizeIdx=constrain(sToInt(nc+1,s1),0,3);
        buttons[page][idx].borderStyle=constrain(sToInt(s1+1,s2),0,3);
        buttons[page][idx].showLabel=sToInt(s2+1,sLen)!=0;
      }
    }
    saveOne(page,idx);
    if(page==currentPage&&!infoShown)drawButton(idx,false);
    Serial.println("OK");return;
  }

  // ACT:<page>:<idx>:<type>:<action>
  if(sLen>=4&&memcmp(sBuf,"ACT:",4)==0){
    int p1=sFindCh(':',4);if(p1<0)return;
    int p2=sFindCh(':',p1+1);if(p2<0)return;
    int p3=sFindCh(':',p2+1);if(p3<0)return;
    int page=sToInt(4,p1);if(page<0||page>=NUM_PAGES)return;
    int idx=sToInt(p1+1,p2);if(idx<0||idx>=NUM_BUTTONS)return;
    buttons[page][idx].actionType=sToInt(p2+1,p3);
    int al=min(sLen-p3-1,127);memcpy(buttons[page][idx].action,sBuf+p3+1,al);buttons[page][idx].action[al]='\0';
    saveOne(page,idx);
    Serial.println("OK");return;
  }

  // ICON:<page>:<idx>:<size>:<base64>
  if(sLen>=5&&memcmp(sBuf,"ICON:",5)==0){
    int p1=sFindCh(':',5);if(p1<0)return;
    int p2=sFindCh(':',p1+1);if(p2<0)return;
    int p3=sFindCh(':',p2+1);if(p3<0)return;
    int page=sToInt(5,p1);if(page<0||page>=NUM_PAGES)return;
    int idx=sToInt(p1+1,p2);if(idx<0||idx>=NUM_BUTTONS)return;
    int ps=sToInt(p2+1,p3);if(ps<16||ps>64)return;
    int eb=ps*ps*2;
    Serial.printf("[ICON] p=%d idx=%d sz=%d b64=%d\n",page,idx,ps,sLen-p3-1);
    if(iconData[page][idx])free(iconData[page][idx]);
    iconData[page][idx]=(uint16_t*)ps_malloc(eb);
    if(!iconData[page][idx]){Serial.println("ERR:MEM");return;}
    int d=base64_decode(sBuf+p3+1,sLen-p3-1,(uint8_t*)iconData[page][idx],eb);
    Serial.printf("[ICON] dec=%d exp=%d\n",d,eb);
    if(d>=eb){
      hasIcon[page][idx]=true;iconPixelSize[page][idx]=ps;
      if(page==currentPage&&!infoShown)drawButton(idx,false);
      Serial.println("OK");
    } else {
      hasIcon[page][idx]=false;Serial.printf("ERR:DEC:%d/%d\n",d,eb);
    }
    return;
  }

  // NOICON:<page>:<idx>
  if(sLen>=7&&memcmp(sBuf,"NOICON:",7)==0){
    int p1=sFindCh(':',7);if(p1<0)return;
    int page=sToInt(7,p1);int idx=atoi(sBuf+p1+1);
    if(page>=0&&page<NUM_PAGES&&idx>=0&&idx<NUM_BUTTONS){
      hasIcon[page][idx]=false;
      if(page==currentPage&&!infoShown)drawButton(idx,false);
    }
    Serial.println("OK");return;
  }

  // PAGE:<n>
  if(sLen>=5&&memcmp(sBuf,"PAGE:",5)==0){
    int np=atoi(sBuf+5);
    if(np>=0&&np<NUM_PAGES){changePage(np);Serial.println("OK");}
    else Serial.println("ERR:RANGE");
    return;
  }

  if(sLen==6&&memcmp(sBuf,"STATUS",6)==0){Serial.printf("BLE:%s\n",bleKb.isConnected()?"CONNECTED":"WAITING");Serial.printf("CURPAGE:%d\n",currentPage);Serial.println("END");return;}
  if(sLen==7&&memcmp(sBuf,"TESTBLE",7)==0){if(bleKb.isConnected()){bleKb.print("StreamDeck OK! ");Serial.println("SENT");}else Serial.println("NOBLE");return;}
  if(sLen==4&&memcmp(sBuf,"PING",4)==0){Serial.println("PONG");return;}
}

void handleSerial(){
  while(Serial.available()){
    char c=Serial.read();
    if(c=='\n'){processCmd();sLen=0;}
    else if(c!='\r'&&sLen<(int)sizeof(sBuf)-1){sBuf[sLen++]=c;}
  }
}

// ─── Info / Setup screen ───
void drawInfoScreen(){
  lcd.fillRect(0,0,GRID_W,480,lcd.color565(15,15,30));
  lcd.setTextDatum(middle_center);

  lcd.setTextColor(lcd.color565(100,126,234));lcd.setFont(&fonts::Font4);
  lcd.drawString("DIY Stream Deck",GRID_W/2,40);
  lcd.setTextColor(lcd.color565(120,120,140));lcd.setFont(&fonts::Font2);
  lcd.drawString("Linux edition",GRID_W/2,65);

  lcd.fillRoundRect(30,95,GRID_W-60,80,12,lcd.color565(25,30,50));
  lcd.drawRoundRect(30,95,GRID_W-60,80,12,lcd.color565(100,126,234));
  lcd.setTextColor(lcd.color565(180,180,200));lcd.setFont(&fonts::Font2);
  lcd.drawString("Repo:",GRID_W/2,115);
  lcd.setTextColor(TFT_WHITE);lcd.setFont(&fonts::Font4);
  lcd.drawString("github.com/gorkaFM",GRID_W/2,142);
  lcd.setTextColor(lcd.color565(200,200,220));
  lcd.drawString("/diy-streamdeck",GRID_W/2,165);

  int sy=200;
  lcd.setFont(&fonts::Font2);
  const char* steps[]={
    "1. Conecta el USB al PC",
    "2. Abre la app Stream Deck Linux",
    "3. Configura tus botones por pagina",
    "4. Desliza para cambiar de pagina",
    "5. Empareja BT 'StreamDeck' para teclado",
    "",
    "3 paginas x 12 botones = 36 acciones",
    "Toca para volver"
  };
  for(int i=0;i<8;i++){
    lcd.setTextColor(i<5?lcd.color565(200,200,210):i==5?0:lcd.color565(100,150,200));
    lcd.drawString(steps[i],GRID_W/2,sy+i*28);
  }

  infoShown=true;
}

void hideInfoScreen(){infoShown=false;drawAll();}

// ─── Touch state machine ───
void onTouchStart(int32_t tx,int32_t ty){
  tStartX=tLastX=tx;tStartY=tLastY=ty;
  tBtn=-1;tSb=-1;
  if(infoShown){
    tphase=TP_PRESS;
    return;
  }
  if(tx>=SB_X){
    tSb=sidebarHitTest(tx,ty);
    tphase=TP_PRESS;
  } else {
    if(!locked){
      tBtn=hitTest(tx,ty);
      if(tBtn>=0)drawButton(tBtn,true);
    }
    tphase=TP_PRESS;
  }
}

void onTouchMove(int32_t tx,int32_t ty){
  tLastX=tx;tLastY=ty;
  if(tphase==TP_PRESS){
    int32_t dx=tx-tStartX, dy=ty-tStartY;
    // If moved horizontally on grid area: enter SWIPE
    if(tStartX<SB_X && abs(dx)>SWIPE_DX/2 && abs(dy)<SWIPE_MAX_DY){
      tphase=TP_SWIPE;
      if(tBtn>=0){drawButton(tBtn,false);tBtn=-1;}
      return;
    }
    // If moved off the touched button: cancel press feedback
    if(tBtn>=0 && (abs(dx)>TAP_TOLERANCE||abs(dy)>TAP_TOLERANCE)){
      drawButton(tBtn,false);tBtn=-1;
    }
  }
}

void onTouchEnd(){
  int32_t dx=tLastX-tStartX, dy=tLastY-tStartY;
  if(tphase==TP_SWIPE){
    if(abs(dx)>=SWIPE_DX && abs(dy)<SWIPE_MAX_DY){
      // dx>0 finger moved right -> previous page (wrap)
      int np=currentPage + (dx<0?1:-1);
      if(np<0)np=NUM_PAGES-1;
      if(np>=NUM_PAGES)np=0;
      changePage(np);
    }
  } else if(tphase==TP_PRESS){
    if(infoShown && tStartX<SB_X){hideInfoScreen();}
    else if(tSb>=0){handleSidebarTouch(tSb,tStartX);}
    else if(tBtn>=0 && abs(dx)<=TAP_TOLERANCE && abs(dy)<=TAP_TOLERANCE){
      drawButton(tBtn,false);
      executeAction(tBtn);
    } else if(tBtn>=0){
      drawButton(tBtn,false);
    }
  }
  tphase=TP_IDLE;tBtn=-1;tSb=-1;
}

// ─── Main ───
void setup(){
  Serial.begin(115200);Serial.setRxBufferSize(16384);
  delay(500);Serial.println("[BOOT] Starting...");
  lcd.init();lcd.setRotation(0);
  for(int p=0;p<NUM_PAGES;p++){
    for(int i=0;i<NUM_BUTTONS;i++){
      iconData[p][i]=NULL;hasIcon[p][i]=false;iconPixelSize[p][i]=32;
      buttons[p][i].action[0]='\0';buttons[p][i].actionType=0;
    }
  }
  loadConfig();lcd.setBrightness(brightness);

  // First boot: show info if no actions configured anywhere
  bool anyAction=false;
  for(int p=0;p<NUM_PAGES&&!anyAction;p++)
    for(int i=0;i<NUM_BUTTONS&&!anyAction;i++)
      if(buttons[p][i].actionType>0)anyAction=true;
  drawAll();
  if(!anyAction)drawInfoScreen();

  Serial.println("[BOOT] Starting BLE...");
  bleKb.begin();
  Serial.println("[BOOT] Ready!");
}

void loop(){
  handleSerial();
  static bool lastBle=false;bool curBle=bleKb.isConnected();
  if(curBle!=lastBle){lastBle=curBle;drawSidebar();Serial.printf("[BLE] %s\n",curBle?"Connected":"Disconnected");}

  int32_t tx,ty;bool touched=lcd.getTouch(&tx,&ty);
  if(touched){
    if(tphase==TP_IDLE){onTouchStart(tx,ty);}
    else{onTouchMove(tx,ty);}
  } else {
    if(tphase!=TP_IDLE){onTouchEnd();}
  }
  delay(10);
}
