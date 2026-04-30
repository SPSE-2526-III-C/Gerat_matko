class Roman:

	def arabicToRoman(arabic: int) -> str:
		if not isinstance(arabic, int):
			return "NIC"
		if arabic <= 0 or arabic > 3999:
			return "NIC"

		pairs = [
			(1000, "M"),
			(900, "CM"),
			(500, "D"),
			(400, "CD"),
			(100, "C"),
			(90, "XC"),
			(50, "L"),
			(40, "XL"),
			(10, "X"),
			(9, "IX"),
			(5, "V"),
			(4, "IV"),
			(1, "I"),
		]

		result = []
		value = arabic
		for num, sym in pairs:
			while value >= num:
				result.append(sym)
				value -= num

		return "".join(result)

	def romanToArabic(roman: str) -> int:
		if not isinstance(roman, str):
			return -9999
		text = roman.strip().upper()
		if text == "":
			return -9999

		values = {
			"I": 1,
			"V": 5,
			"X": 10,
			"L": 50,
			"C": 100,
			"D": 500,
			"M": 1000,
		}

		total = 0
		i = 0
		while i < len(text):
			if text[i] not in values:
				return -9999
			if i + 1 < len(text) and text[i + 1] in values:
				if values[text[i]] < values[text[i + 1]]:
					total += values[text[i + 1]] - values[text[i]]
					i += 2
					continue
			total += values[text[i]]
			i += 1

		if total <= 0 or total > 3999:
			return -9999

		if Roman.arabicToRoman(total) != text:
			return -9999

		return total
