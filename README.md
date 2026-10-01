# Super Hexagon 540 Hz

Patcher para a versão Windows (Neo) do Super Hexagon no Steam que roda o jogo inteiro acima de 60 FPS
(120, 240, 360, 540 Hz ou qualquer múltiplo de 60 até 960) mantendo as regras do jogo original.

Patcher for the Windows (Neo) Steam build of Super Hexagon that runs the whole game above 60 FPS
(any multiple of 60 up to 960 Hz) while keeping the original game rules.

## Download

Na página de [Releases](../../releases) há duas opções que fazem exatamente a mesma coisa:

- `SuperHexagon540Patcher.exe`: programa para Windows, não precisa instalar nada.
- `superhexagon540.py`: o mesmo patcher em um único script Python 3, para quem prefere ler o código antes de rodar
  (`python superhexagon540.py`).

Coloque o arquivo na pasta do jogo (Steam: botão direito no Super Hexagon, Gerenciar, Procurar arquivos locais),
feche o jogo e rode. Opção 1 aplica 540 Hz, opção 2 escolhe outra taxa, opção 3 restaura o original.
Linha de comando: `--hz 240`, `--restore`, `--status`, `--lang en` ou `--lang pt`.

O patcher abre no idioma do Windows (português ou inglês) e a opção 4 do menu troca o idioma.
The patcher starts in the Windows language (English or Portuguese); menu option 4 switches language.

## O que o patcher faz

1. Procura o `SuperHexagon.exe` na mesma pasta (ou na pasta passada como argumento).
2. Calcula o SHA-256 do arquivo e só continua se for a versão suportada:
   `72b0c26053c37edd3435def461e9027cd6ffad12032db2fd0b32c256fdbee6b9` (1.467.904 bytes).
3. Cria `SuperHexagon.exe.bak` com o original, se ainda não existir um backup válido.
4. Grava um novo `SuperHexagon.exe`: o original com pequenos trechos de código desviados e duas seções novas,
   `.sh540d` (dados, leitura e escrita) e `.sh540c` (código, leitura e execução), com a modificação.
5. Restaurar copia o `.bak` de volta.

O que ele não faz: não acessa a internet, não pede administrador, não mexe no registro, não instala nada,
não altera nenhum outro arquivo e não roda em segundo plano. O `.exe` só importa `KERNEL32.dll` e `msvcrt.dll`.

## Compilar

```
i686-w64-mingw32-windres --input-format=rc -O coff -i patcher.rc -o patcher_res.o
i686-w64-mingw32-gcc -O2 -s -Wl,--no-insert-timestamp -o SuperHexagon540Patcher.exe patcher.c patcher_res.o
```

`patchdata.h` já vem pronto. Para regerá-lo do zero você precisa da sua cópia do `SuperHexagon.exe` na pasta,
de Python 3 e do GNU as/ld (binutils): `python3 genpatch.py`.

`build540.py` contém todo o código assembly da modificação, com comentários sobre cada ponto do jogo alterado.

## Verificação

SHA-256 do `SuperHexagon540Patcher.exe` da versão 2.0:
`b4af7391fa3e7bb1db7a219d5448bb8e154ca5e14bd18285094b9af26bea1af6`

A compilação é reproduzível: com o MinGW-w64 (GCC 13, binutils 2.42) os comandos acima geram o mesmo hash.

## Como funciona

O jogo já calcula quase tudo em função de um delta por atualização, mas no PC ele trava esse delta em 1.0 e roda
um loop fixo de 60 Hz. O patch roda o loop a 60×N Hz com passos de k/64 que somam exatamente 1.0 a cada tick de
60 Hz, e faz os eventos discretos (colisão, padrões, giros, pausas, troca de forma, rank) acontecerem uma vez por
tick, como no original. A colisão é decidida com as posições das paredes do início do tick, como no jogo de 60 Hz.

A validação foi feita comparando, tick a tick, o estado do jogo original e do modificado com a mesma semente,
com e sem jogador, nos seis níveis.

Não contém nem distribui arquivos do jogo. Super Hexagon é de Terry Cavanagh, músicas de Chipzel.
Inspirado pelo [SuperHexagonFPSUnlocker](https://github.com/tarkodev/SuperHexagonFPSUnlocker) de tarkodev.
