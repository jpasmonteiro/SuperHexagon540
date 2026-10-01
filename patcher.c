/* SuperHexagon 540 Hz patcher v2.0
   Applies to the local copy of the game (Steam Neo build) the modification that runs the
   simulation at 60*N Hz with the original rules. Does not distribute any game files.
   Aplica na cópia local do jogo a modificação que roda a simulação a 60*N Hz. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "patchdata.h"

/* ---------------- SHA-256 ---------------- */
typedef struct { uint32_t s[8]; uint64_t len; uint8_t buf[64]; size_t n; } sha_t;
static const uint32_t K[64]={0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,
0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,
0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,
0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,
0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define ROR(x,n) (((x)>>(n))|((x)<<(32-(n))))
static void sha_blk(sha_t*c,const uint8_t*p){uint32_t w[64],a,b,d,e,f,g,h,cc,t1,t2;int i;
 for(i=0;i<16;i++)w[i]=(uint32_t)p[4*i]<<24|(uint32_t)p[4*i+1]<<16|(uint32_t)p[4*i+2]<<8|p[4*i+3];
 for(;i<64;i++)w[i]=(ROR(w[i-2],17)^ROR(w[i-2],19)^(w[i-2]>>10))+w[i-7]+(ROR(w[i-15],7)^ROR(w[i-15],18)^(w[i-15]>>3))+w[i-16];
 a=c->s[0];b=c->s[1];cc=c->s[2];d=c->s[3];e=c->s[4];f=c->s[5];g=c->s[6];h=c->s[7];
 for(i=0;i<64;i++){t1=h+(ROR(e,6)^ROR(e,11)^ROR(e,25))+((e&f)^(~e&g))+K[i]+w[i];t2=(ROR(a,2)^ROR(a,13)^ROR(a,22))+((a&b)^(a&cc)^(b&cc));
  h=g;g=f;f=e;e=d+t1;d=cc;cc=b;b=a;a=t1+t2;}
 c->s[0]+=a;c->s[1]+=b;c->s[2]+=cc;c->s[3]+=d;c->s[4]+=e;c->s[5]+=f;c->s[6]+=g;c->s[7]+=h;}
static void sha_hex(const uint8_t*p,size_t n,char out[65]){sha_t c={{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19},0,{0},0};
 size_t i; uint8_t pad[128]; size_t full=n/64*64; for(i=0;i<full;i+=64)sha_blk(&c,p+i);
 size_t r=n-full; memset(pad,0,128); memcpy(pad,p+full,r); pad[r]=0x80; size_t tot=(r<56)?64:128; uint64_t bits=(uint64_t)n*8;
 for(i=0;i<8;i++)pad[tot-1-i]=(uint8_t)(bits>>(8*i)); for(i=0;i<tot;i+=64)sha_blk(&c,pad+i);
 for(i=0;i<8;i++)sprintf(out+8*i,"%08x",c.s[i]); out[64]=0;}

/* ---------------- files ---------------- */
static uint8_t *read_file(const char *path, size_t *n){
    FILE *f=fopen(path,"rb"); if(!f) return NULL;
    fseek(f,0,SEEK_END); long sz=ftell(f); fseek(f,0,SEEK_SET);
    uint8_t *b=malloc(sz>0?sz:1); if(fread(b,1,sz,f)!=(size_t)sz){fclose(f);free(b);return NULL;}
    fclose(f); *n=sz; return b;
}
static int write_file(const char *path, const uint8_t *b, size_t n){
    FILE *f=fopen(path,"wb"); if(!f) return 0;
    int ok = fwrite(b,1,n,f)==n; ok = (fclose(f)==0) && ok; return ok;
}
static int is_original(const uint8_t *b, size_t n){
    char h[65]; if(n!=ORIG_SIZE) return 0; sha_hex(b,n,h); return strcmp(h,ORIG_SHA)==0;
}
static int patched_n(const uint8_t *b, size_t n){       /* returns N if this looks like our patch (any version) */
    if(n<ORIG_SIZE+0x100) return 0;
    if(memcmp(b+ORIG_SIZE,"SH540PAT",8)) return 0;
    int32_t v; memcpy(&v,b+ORIG_SIZE+OFF_N,4); return v;
}
static int patched_version(const uint8_t *b){ int32_t v; memcpy(&v,b+ORIG_SIZE+OFF_VERSION,4); return v; }

static void table_for(int n, uint8_t *t){
    int base=64/n, extra=64%n, acc=0;
    for(int i=0;i<n;i++){ acc+=extra; if(acc>=n){acc-=n;t[i]=base+1;} else t[i]=base; }
}
static uint8_t *make_patched(const uint8_t *orig, int n, size_t *outn){
    uint8_t *o=malloc(ORIG_SIZE+SEC_SIZE); memcpy(o,orig,ORIG_SIZE);
    const uint8_t *d=RUN_DATA;
    for(int i=0;i<NRUNS;i++){ memcpy(o+RUN_OFF[i],d,RUN_LEN[i]); d+=RUN_LEN[i]; }
    uint8_t *s=o+ORIG_SIZE; memcpy(s,SEC_BLOB,SEC_SIZE);
    int32_t nn=n, idx=n-1; memcpy(s+OFF_N,&nn,4); memcpy(s+OFF_IDX,&idx,4);
    memset(s+OFF_TABLE,0,16); table_for(n,s+OFF_TABLE);
    *outn=ORIG_SIZE+SEC_SIZE; return o;
}

/* ---------------- language / idioma ---------------- */
#define PATCHER_VERSION "2.0"
enum { EN=0, PT=1 };
static int lang = EN;
enum { S_GAME, S_CANTREAD, S_ORIG, S_PATCHED, S_OLDPATCH, S_UNKNOWN, S_BADRATE, S_CLOSE_APPLY, S_CANTREADF,
       S_UNSUPPORTED, S_CANTBACKUP, S_BACKUP, S_DONE, S_WRITEFAIL, S_CLOSE_RESTORE, S_ALREADY, S_NOBACKUP,
       S_RESTORED, S_RESTOREFAIL, S_ENTER, S_NOTFOUND, S_MENU, S_RATE, S_COUNT };
static const char *STR[S_COUNT][2] = {
 {"Game: %s\n", "Jogo: %s\n"},
 {"State: could not read the executable.\n", "Estado: não consegui ler o executável.\n"},
 {"State: original (60 Hz)\n", "Estado: original (60 Hz)\n"},
 {"State: patched at %d Hz\n", "Estado: modificado a %d Hz\n"},
 {"State: patched at %d Hz with an older patch (v%d). Apply again to update.\n",
  "Estado: modificado a %d Hz com uma versão antiga do patch (v%d). Aplique de novo para atualizar.\n"},
 {"State: unknown version (Steam update or modified by another tool)\n",
  "Estado: versão desconhecida (atualização do Steam ou modificado por outra ferramenta)\n"},
 {"The rate must be a multiple of 60 between 120 and 960.\n", "A taxa precisa ser múltiplo de 60 entre 120 e 960.\n"},
 {"Close the game before applying.\n", "Feche o jogo antes de aplicar.\n"},
 {"Could not read %s\n", "Não consegui ler %s\n"},
 {"This SuperHexagon.exe is not the supported version and there is no original backup.\n"
  "Verify the integrity of the game files in Steam and try again.\n",
  "Este SuperHexagon.exe não é a versão suportada e não há backup original.\n"
  "Verifique a integridade dos arquivos no Steam e tente de novo.\n"},
 {"Could not create the backup %s\n", "Não consegui criar o backup %s\n"},
 {"Backup created: %s\n", "Backup criado: %s\n"},
 {"Done: game patched for %d Hz.\n", "Pronto: jogo modificado para %d Hz.\n"},
 {"Failed to write %s\n", "Falha ao gravar %s\n"},
 {"Close the game before restoring.\n", "Feche o jogo antes de restaurar.\n"},
 {"The game is already original.\n", "O jogo já está original.\n"},
 {"Original backup not found. Use \"Verify integrity of game files\" in Steam.\n",
  "Backup original não encontrado. Use \"Verificar integridade dos arquivos\" no Steam.\n"},
 {"Original restored (60 Hz).\n", "Original restaurado (60 Hz).\n"},
 {"Restore failed.\n", "Falha ao restaurar.\n"},
 {"\nPress Enter to exit...", "\nPressione Enter para sair..."},
 {"Could not find SuperHexagon.exe.\nPut this patcher in the game folder or pass the folder as an argument.\n",
  "Não encontrei o SuperHexagon.exe.\nColoque este patcher na pasta do jogo ou passe a pasta como argumento.\n"},
 {"\n[1] Apply 540 Hz\n[2] Choose another rate (multiple of 60: 120, 240, 360, 480, 600...)\n[3] Restore original (60 Hz)\n[4] Idioma: Português\n[0] Exit\n> ",
  "\n[1] Aplicar 540 Hz\n[2] Escolher outra taxa (múltiplo de 60: 120, 240, 360, 480, 600...)\n[3] Restaurar original (60 Hz)\n[4] Language: English\n[0] Sair\n> "},
 {"Rate in Hz: ", "Taxa em Hz: "},
};
#define T(id) STR[id][lang]

static void detect_lang(void){
    LANGID id = GetUserDefaultUILanguage();
    lang = (PRIMARYLANGID(id) == LANG_PORTUGUESE) ? PT : EN;
}

static char exe_path[MAX_PATH], bak_path[MAX_PATH+8];

static int game_running(void){
    HANDLE h=CreateFileA(exe_path,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_EXISTING,0,NULL);
    if(h==INVALID_HANDLE_VALUE) return GetLastError()==ERROR_SHARING_VIOLATION;
    CloseHandle(h); return 0;
}

static int find_exe(const char *arg){
    char dir[MAX_PATH];
    if(arg && *arg){
        snprintf(exe_path,sizeof exe_path,"%s",arg);
        DWORD a=GetFileAttributesA(exe_path);
        if(a!=INVALID_FILE_ATTRIBUTES && (a&FILE_ATTRIBUTE_DIRECTORY)){
            size_t l=strlen(exe_path); snprintf(exe_path+l,sizeof exe_path-l,"%sSuperHexagon.exe",(exe_path[l-1]=='\\'||exe_path[l-1]=='/')?"":"\\");
        }
    } else {
        GetModuleFileNameA(NULL,dir,MAX_PATH); char *p=strrchr(dir,'\\'); if(p)*p=0;
        snprintf(exe_path,sizeof exe_path,"%s\\SuperHexagon.exe",dir);
        if(GetFileAttributesA(exe_path)==INVALID_FILE_ATTRIBUTES){
            GetCurrentDirectoryA(MAX_PATH,dir); snprintf(exe_path,sizeof exe_path,"%s\\SuperHexagon.exe",dir);
        }
    }
    snprintf(bak_path,sizeof bak_path,"%s.bak",exe_path);
    return GetFileAttributesA(exe_path)!=INVALID_FILE_ATTRIBUTES;
}

/* returns malloc'd original image or NULL */
static uint8_t *get_original(const uint8_t *cur, size_t curn){
    size_t n; uint8_t *b;
    if(is_original(cur,curn)){ b=malloc(curn); memcpy(b,cur,curn); return b; }
    b=read_file(bak_path,&n);
    if(b && is_original(b,n)) return b;
    free(b); return NULL;
}

static void status(void){
    size_t n; uint8_t *b=read_file(exe_path,&n);
    printf(T(S_GAME),exe_path);
    if(!b){ printf("%s",T(S_CANTREAD)); return; }
    int pn=patched_n(b,n);
    if(is_original(b,n)) printf("%s",T(S_ORIG));
    else if(pn && patched_version(b)==PATCH_VERSION) printf(T(S_PATCHED),pn*60);
    else if(pn) printf(T(S_OLDPATCH),pn*60,patched_version(b));
    else printf("%s",T(S_UNKNOWN));
    free(b);
}

static int do_patch(int hz){
    if(hz%60 || hz<120 || hz>960){ printf("%s",T(S_BADRATE)); return 1; }
    if(game_running()){ printf("%s",T(S_CLOSE_APPLY)); return 1; }
    size_t n; uint8_t *cur=read_file(exe_path,&n);
    if(!cur){ printf(T(S_CANTREADF),exe_path); return 1; }
    uint8_t *orig=get_original(cur,n);
    if(!orig){ printf("%s",T(S_UNSUPPORTED)); free(cur); return 1; }
    /* backup: keep a valid original .bak */
    size_t bn; uint8_t *bb=read_file(bak_path,&bn);
    if(!(bb && is_original(bb,bn))){
        if(!write_file(bak_path,orig,ORIG_SIZE)){ printf(T(S_CANTBACKUP),bak_path); free(bb);free(cur);free(orig); return 1; }
        printf(T(S_BACKUP),bak_path);
    }
    free(bb);
    size_t pn; uint8_t *p=make_patched(orig,hz/60,&pn);
    int ok=write_file(exe_path,p,pn);
    if(ok) printf(T(S_DONE),hz);
    else printf(T(S_WRITEFAIL),exe_path);
    free(p); free(cur); free(orig); return ok?0:1;
}

static int do_restore(void){
    if(game_running()){ printf("%s",T(S_CLOSE_RESTORE)); return 1; }
    size_t n; uint8_t *cur=read_file(exe_path,&n);
    if(cur && is_original(cur,n)){ printf("%s",T(S_ALREADY)); free(cur); return 0; }
    free(cur);
    uint8_t *b=read_file(bak_path,&n);
    if(!(b && is_original(b,n))){ printf("%s",T(S_NOBACKUP)); free(b); return 1; }
    int ok=write_file(exe_path,b,n); free(b);
    printf("%s",ok?T(S_RESTORED):T(S_RESTOREFAIL)); return ok?0:1;
}

static void pause_exit(void){ printf("%s",T(S_ENTER)); fflush(stdout); getchar(); }

int main(int argc, char **argv){
    SetConsoleOutputCP(65001);
    detect_lang();
    const char *path=NULL; int hz=0, restore=0, stat=0;
    for(int i=1;i<argc;i++){
        if(!strcmp(argv[i],"--hz") && i+1<argc) hz=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--restore")) restore=1;
        else if(!strcmp(argv[i],"--status")) stat=1;
        else if(!strcmp(argv[i],"--lang") && i+1<argc){ i++; lang = (!_stricmp(argv[i],"pt")||!_stricmp(argv[i],"pt-br")) ? PT : EN; }
        else path=argv[i];
    }
    printf("SuperHexagon 540 Hz patcher v%s (patch v%d)\n\n",PATCHER_VERSION,PATCH_VERSION);
    if(!find_exe(path)){
        printf("%s",T(S_NOTFOUND));
        if(argc<2) pause_exit(); return 1;
    }
    if(stat){ status(); return 0; }
    if(restore) return do_restore();
    if(hz) return do_patch(hz);
    for(;;){
        status();
        printf("%s",T(S_MENU));
        fflush(stdout);
        char line[64]; if(!fgets(line,sizeof line,stdin)) return 0;
        int c=atoi(line);
        if(c==1) do_patch(540);
        else if(c==2){ printf("%s",T(S_RATE)); fflush(stdout); if(fgets(line,sizeof line,stdin)) do_patch(atoi(line)); }
        else if(c==3) do_restore();
        else if(c==4) lang = !lang;
        else if(c==0 || line[0]=='\n') return 0;
        printf("\n");
    }
}
