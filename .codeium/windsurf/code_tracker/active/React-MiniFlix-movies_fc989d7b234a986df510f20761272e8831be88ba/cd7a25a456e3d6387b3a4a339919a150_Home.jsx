Êimport { useEffect, useState } from "react";
import MovieCard from "../components/MovieCard";

export default function Home() {
  const [movies, setMovies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError("");
        const apiKey = import.meta.env.VITE_TMDB_API_KEY; // v3 key
        const readToken = import.meta.env.VITE_TMDB_READ_TOKEN; // v4 read access token

        if (!apiKey && !readToken) {
          setError(
            "TMDB credentials missing. Set VITE_TMDB_API_KEY (v3) or VITE_TMDB_READ_TOKEN (v4) in a .env.local file."
          );
          setMovies([]);
          return;
        }

        const baseUrl = "https://api.themoviedb.org/3/movie/popular?language=en-US&page=1";
        const url = apiKey ? `${baseUrl}&api_key=${apiKey}` : baseUrl;
        const headers = readToken
          ? { Authorization: `Bearer ${readToken}` }
          : undefined;

        const res = await fetch(url, { headers });
        const data = await res.json();
        if (!res.ok || !data.results) {
          const msg = data.status_message || "Failed to load movies.";
          setError(msg);
          setMovies([]);
        } else {
          setMovies(data.results);
        }
      } catch (err) {
        setError("Network error loading movies.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const styles = {
    section: {
      padding: '24px',
      backgroundColor: '#141414',
      color: '#e5e5e5',
    },
    title: {
      fontSize: '22px',
      fontWeight: 700,
      marginBottom: '16px',
    },
    gridGutter: {
      rowGap: '16px',
    },
  };

  if (loading) {
    return (
      <section style={styles.section}><h2 style={styles.title}>Loading‚Ä¶</h2></section>
    );
  }

  return (
    <section style={styles.section}>
      <h2 style={styles.title}>Trending Now</h2>
      {error ? (
        <p style={{ color: '#b3b3b3' }}>{error} Check your TMDB API key or try again later.</p>
      ) : (
        <div className="row" style={styles.gridGutter}>
          {movies.map((movie) => (
            <div className="col-md-3 mb-4" key={movie.id}>
              <MovieCard movie={movie} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
¨ *cascade08¨Ü*cascade08Üü *cascade08ü•*cascade08•¶ *cascade08¶Ã*cascade08ÃŒ *cascade08ŒÌ*cascade08ÌÓ *cascade08ÓÚ*cascade08ÚÛ *cascade08ÛÅ *cascade08Å± *cascade08±∑*cascade08∑Ú *cascade08ÚÙ *cascade08Ù˛*cascade08˛ˇ *cascade08ˇÅ*cascade08ÅÜ *cascade08Üä *cascade08äè*cascade08èê *cascade08êô*cascade08ô∆ *cascade08∆á*cascade08áè *cascade08èï*cascade08ïñ *cascade08ñú*cascade08úû *cascade08ûü*cascade08ü† *cascade08†µ*cascade08µ∑ *cascade08∑ø*cascade08ø¿ *cascade08¿≈*cascade08≈∆ *cascade08∆÷*cascade08÷◊ *cascade08◊›*cascade08›ﬁ *cascade08ﬁÊ*cascade08ÊÁ *cascade08ÁÔ*cascade08ÔÒ *cascade08Òı*cascade08ıˆ *cascade08ˆë*cascade08ëí*cascade08íì*cascade08ìú *cascade08ú°*cascade08°® *cascade08®Ø*cascade08Ø∞ *cascade08∞≥*cascade08≥¥ *cascade08¥∑*cascade08∑ƒ*cascade08ƒ≈ *cascade08≈∆*cascade08∆Õ *cascade08Õ”*cascade08”‘ *cascade08‘’*cascade08’‹ *cascade08‹Ì*cascade08Ì˙ *cascade08˙Ü	*cascade08Ü	†	 *cascade08†	£	*cascade08£	•	 *cascade08•	ß	*cascade08ß	®	 *cascade08®	¨	*cascade08¨	≤	 *cascade08≤	µ	*cascade08µ	∂	 *cascade08∂	«	*cascade08«	»	 *cascade08»	À	*cascade08À	Ã	 *cascade08Ã	ÿ	*cascade08ÿ	Ÿ	 *cascade08Ÿ	€	*cascade08€	‹	 *cascade08‹	ﬂ	*cascade08ﬂ	‡	 *cascade08‡	Â	*cascade08Â	Á	 *cascade08Á	Ë	*cascade08Ë	Í	 *cascade08Í	Î	*cascade08Î	Ï	 *cascade08Ï	Ò	*cascade08Ò	Ú	 *cascade08Ú	˝	*cascade08˝	˛	 *cascade08˛	á
*cascade08á
â
 *cascade08â
ö
*cascade08ö
ú
 *cascade08ú
ù
*cascade08ù
û
 *cascade08û
ü
*cascade08ü
®
 *cascade08®
¬
*cascade08¬
√
 *cascade08√
ƒ
*cascade08ƒ
 
 *cascade08 
À
*cascade08À
”
 *cascade08”
’
*cascade08’
⁄
 *cascade08⁄
€
*cascade08€
·
 *cascade08·
Í
*cascade08Í
Ì
 *cascade08Ì
Ô
*cascade08Ô
ı
 *cascade08ı
˛
*cascade08˛
É *cascade08Éá*cascade08áë *cascade08ëí*cascade08íì *cascade08ìÆ*cascade08ÆØ *cascade08Ø±*cascade08±≤ *cascade08≤¿*cascade08¿¡ *cascade08¡⁄*cascade08⁄¯ *cascade08¯˚*cascade08˚» *cascade08»–*cascade08–— *cascade08—“*cascade08“” *cascade08”·*cascade08·‚ *cascade08‚Ï*cascade08ÏÌ *cascade08Ì˜*cascade08˜¯ *cascade08¯Ç*cascade08ÇÑ *cascade08Ñù*cascade08ùû *cascade08û∆*cascade08∆» *cascade08»…*cascade08…— *cascade08—ﬂ*cascade08ﬂè *cascade08èë*cascade08ëº *cascade08ºæ*cascade08æ˘ *cascade08˘˚*cascade08˚ó *cascade08óô*cascade08ô≤ *cascade08≤¥*cascade08¥∏ *cascade08∏∫*cascade08∫∆ *cascade08∆œ*cascade08œÊ *cascade08"(fc989d7b234a986df510f20761272e8831be88ba2Efile:///Users/dam113/Desktop/React-MiniFlix-movies/src/pages/Home.jsx:2file:///Users/dam113/Desktop/React-MiniFlix-movies