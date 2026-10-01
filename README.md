# Super Hexagon 540 Hz

Patcher para a versão Windows (Neo) do Super Hexagon no Steam que roda o jogo inteiro acima de 60 FPS
(120, 240, 360, 540 Hz ou qualquer múltiplo de 60 até 960) mantendo as regras do jogo original.

Patcher for the Windows (Neo) Steam build of Super Hexagon that runs the whole game above 60 FPS
(any multiple of 60 up to 960 Hz) while keeping the original game rules.

## O que o SuperHexagon540Patcher.exe faz

1. Procura o `SuperHexagon.exe` na mesma pasta (ou na pasta passada como argumento).
2. Calcula o SHA-256 do arquivo e só continua se for a versão suportada:
   `72b0c26053c37edd3435def461e9027cd6ffad12032db2fd0b32c256fdbee6b9` (1.467.904 bytes).
3. Cria `SuperHexagon.exe.bak` com o original, se ainda não existir um backup válido.
4. Grava um novo `SuperHexagon.exe`: o original com 63 trechos pequenos de código desviados e uma seção
   nova (`.sh540`, 16 KB) com o código da modificação.
5. Restaurar (`--restore` ou opção 3) copia o `.bak` de volta.

O que ele não faz: não acessa a internet, não pede administrador, não mexe no registro, não instala nada,
não altera nenhum outro arquivo e não roda em segundo plano. O código-fonte completo está aqui.

## Compilar

```
i686-w64-mingw32-gcc -O2 -static -Wl,--no-insert-timestamp -o SuperHexagon540Patcher.exe patcher.c
```

`patchdata.h` já vem pronto. Para regerá-lo a partir do zero você precisa da sua cópia do
`SuperHexagon.exe` na pasta, de Python 3 e do GNU as/ld (binutils):

```
python3 genpatch.py
```

`build540.py` contém todo o código assembly da modificação, com comentários sobre cada ponto do jogo
alterado.

## Como funciona

O jogo já calcula quase tudo em função de um delta por atualização, mas no PC ele trava esse delta em 1.0 e
roda um loop fixo de 60 Hz. O patch roda o loop a 60×N Hz com passos de k/64 que somam exatamente 1.0 a
cada tick de 60 Hz, e faz os eventos discretos (colisão, padrões, giros, pausas, troca de forma, rank)
acontecerem uma vez por tick, como no original. A validação foi feita comparando, tick a tick, o estado do
jogo original e do modificado com a mesma semente, com e sem jogador, nos seis níveis.

Não contém nem distribui arquivos do jogo. Super Hexagon é de Terry Cavanagh, músicas de Chipzel.
Inspirado pelo SuperHexagonFPSUnlocker de tarkodev (github.com/tarkodev/SuperHexagonFPSUnlocker).

## Verificação / Verification

SHA-256 do `SuperHexagon540Patcher.exe` publicado:
`978bc3eb2c18f6851b02e7695f8198a82c468e3ebdcf4f161eefcb647ea96885`

A compilação é reproduzível: com o mesmo MinGW (GCC 13, binutils 2.42) o comando acima gera o mesmo hash.
