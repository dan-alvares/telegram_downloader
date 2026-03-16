# Instruções de uso

Antes de utilizar o CLI, é preciso obter chaves de API do Telegram

Para isso, siga os passos:

1) Acesse e realize login no Telegram em: https://my.telegram.org.
2) Depois acesse https://my.telegram.org/apps e preencha os dados do nome da aplicação e nome curto.
3) Salve as informações obtidas **App api_id** e **App api_hash**.
4) Crie um arquivo .env na pasta raiz e preencha da seguinte forma:  

```txt
TG_API_ID=App api_id
TG_API_HASH=App api_hash
DOWNLOAD_SIM=3
```

5) Insira os valores sem aspas, sem espaços e salve o arquivo .env.
6) Se deseja baixar mais que 3 arquivos de maneira simultânea, altere o valor da **variável DOWNLOAD_SIM** no seu arquivo .env
7) Depois basta seguir com a abertura do CLI, obter o link do grupo que deseja baixar seu conteúdo e seguir as instruções em tela.
8) Ao baixar o conteúdo, será criado um diretório com subpastas, exemplo: downloads/<nome do conteúdo baixado>.

## Comandos

``telegram_downloader.exe baixar tudo``

Com este comando você será perguntado em seguida o link para o canal/grupo e o programa baixará todos os vídeos disponíveis, os salvando na pasta downloads/**nome-do-curso**.

``telegram_downloader.exe baixar apenas``

Já este comando baixará apenas os últimos **n** vídeos informados via input prompt do CLI, os salvando na pasta downloads/**nome-do-curso**.

O CLI agora conta com um simples histórico de vídeos. Assim, se por alguma razão o download for interrompido, o programa buscará o ponto que deverá retomar o download, baixando todos os arquivos incompletos.

**Este CLI não é afiliado de qualquer maneira com o Telegram e não me responsabilizo por seu uso.**