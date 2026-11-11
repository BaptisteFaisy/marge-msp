/* API du déploiement de démonstration. Le portail hébergé ailleurs que
 * CloudFront (ex. GitHub Pages) s'en sert ; sur CloudFront il l'ignore et
 * appelle sa propre origine (/v1/*). URL publique, aucun secret. */
window.MARGE_API_BASE = "https://d3n1e2aqabg966.cloudfront.net";
